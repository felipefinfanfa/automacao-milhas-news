#!/usr/bin/env python3
"""Entry point for GitHub Actions: runs the full pipeline for the given tier.

Usage:
    python scripts/run_pipeline.py --tier 1
    python scripts/run_pipeline.py --tier 2
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import traceback
from datetime import UTC, datetime
from typing import Any

import httpx
import sentry_sdk

from src.config.settings import ACCUMULATION_PROGRAMS, VALID_TRANSFER_PAIRS, settings
from src.db.models import (
    AutomationLog,
    EmailLog,
    Promotion,
    create_engine_from_url,
    get_session_factory,
)
from src.pipeline.dedup import dedup_batch
from src.pipeline.dispatcher import dispatch_day1
from src.pipeline.extractor import extract
from src.pipeline.preference_filter import load_all_preferences
from src.tools.user_agents import rotate_ua
from src.types import PromotionData, UserPreferencesData

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.app_env)


def _send_slack_alert(tier: int, error_msg: str) -> None:
    webhook = os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook:
        return
    run_id = os.getenv("GITHUB_RUN_ID", "")
    run_url = (
        f"https://github.com/felipefinfanfa/radar-de-milhas/actions/runs/{run_id}"
        if run_id
        else "N/A"
    )
    payload = {
        "text": (
            f"❌ *Radar de Milhas — Pipeline Error*\n"
            f"Tier: {tier} | Run: <{run_url}|#{run_id}>\n"
            f"Error: {error_msg[:400]}"
        )
    }
    try:
        httpx.post(webhook, json=payload, timeout=10)
    except Exception:
        pass


def _run_monitors(tier: int) -> list[Any]:
    from src.pipeline.monitors.direct_scraper import scan_all_programs
    from src.pipeline.monitors.google_news import scan_google_news
    from src.pipeline.monitors.hash_diff import scan_hash_diff
    from src.pipeline.monitors.rss_monitor import scan_rss

    rotate_ua()
    signals: list[Any] = []
    signals.extend(scan_rss())
    signals.extend(scan_google_news())
    signals.extend(scan_hash_diff())
    signals.extend(scan_all_programs())

    if tier >= 2:
        from src.pipeline.monitors.news_scraper import scan_all_news
        from src.pipeline.monitors.robots_monitor import scan_robots
        from src.pipeline.monitors.sitemap_monitor import scan_sitemap

        signals.extend(scan_sitemap())
        signals.extend(scan_robots())
        signals.extend(scan_all_news())

    return signals


def _is_relevant_promo(promo: PromotionData) -> bool:
    if promo.promo_type == "transfer_bonus":
        origin = (promo.origin_program or promo.source_program or "").lower()
        dest = (promo.destination_program or "").lower()
        return (origin, dest) in VALID_TRANSFER_PAIRS
    program = (promo.origin_program or promo.source_program or "").lower()
    return program in ACCUMULATION_PROGRAMS


def _db_promo_matches_prefs(promo: Any, prefs: UserPreferencesData) -> bool:
    if promo.promo_type == "transfer_bonus":
        if not prefs.transfer_pairs:
            return False
        origin = (promo.origin_program or promo.source_program or "").lower()
        dest = (promo.destination_program or "").lower()
        return any(
            p.source.lower() == origin and p.dest.lower() == dest for p in prefs.transfer_pairs
        )
    program = (promo.origin_program or promo.source_program or "").lower()
    return program in {p.lower() for p in prefs.accumulation_programs}


def _dispatch_emails(session: Any) -> int:
    now = datetime.now(UTC)
    all_prefs = load_all_preferences(session)

    if not all_prefs:
        logger.warning("Nenhuma preferência cadastrada, sem e-mails")
        return 0

    all_active_db: list[Any] = (
        session.query(Promotion)
        .filter(
            Promotion.ends_at.isnot(None),
            Promotion.ends_at > now,
            Promotion.bonus_percent.isnot(None),
            (Promotion.starts_at == None) | (Promotion.starts_at <= now),  # noqa: E711
        )
        .order_by(Promotion.bonus_percent.desc().nullslast())
        .all()
    )

    emails_sent = 0
    for prefs in all_prefs:
        user_email = prefs.email or settings.digest_recipient
        sent_ids = {
            str(row.promo_id)
            for row in session.query(EmailLog.promo_id)
            .filter(EmailLog.user_id == prefs.user_id, EmailLog.day_number == 1)
            .all()
        }
        user_active = [
            p
            for p in all_active_db
            if str(p.id) not in sent_ids and _db_promo_matches_prefs(p, prefs)
        ]
        if user_active:
            sent = dispatch_day1(
                session=session,
                user_id=prefs.user_id,
                user_email=user_email,
                new_promos=user_active,
                unsubscribe_token=prefs.unsubscribe_token,
            )
            if sent:
                emails_sent += 1

    return emails_sent


def main(tier: int) -> None:
    started = time.monotonic()
    engine = create_engine_from_url(settings.database_url)
    SessionFactory = get_session_factory(engine)
    workflow = f"pipeline-tier{tier}"
    gh_run_id = os.getenv("GITHUB_RUN_ID")

    signals_found = promos_new = emails_sent = 0

    try:
        signals = _run_monitors(tier)
        signals_found = len(signals)
        logger.info("Tier %d: %d sinais coletados", tier, signals_found)

        raw_promos: list[PromotionData] = []
        for signal in signals:
            raw_promos.extend(extract(signal))
        raw_promos = [p for p in raw_promos if _is_relevant_promo(p)]
        logger.info("Tier %d: %d promoções relevantes extraídas", tier, len(raw_promos))

        with SessionFactory() as session:
            dedup_results = dedup_batch(session, raw_promos) if raw_promos else []
            new_promos_data = [data for data, is_new in dedup_results if is_new]
            promos_new = len(new_promos_data)
            logger.info("Tier %d: %d promoções novas após dedup", tier, promos_new)

            emails_sent = _dispatch_emails(session)
            logger.info("Tier %d: %d e-mails enviados", tier, emails_sent)

        duration = round(time.monotonic() - started, 2)
        with SessionFactory() as session:
            session.add(
                AutomationLog(
                    workflow=workflow,
                    tier=tier,
                    status="success",
                    signals_found=signals_found,
                    promos_new=promos_new,
                    emails_sent=emails_sent,
                    duration_seconds=duration,
                    gh_run_id=gh_run_id,
                )
            )
            session.commit()
        logger.info("Tier %d completo em %.1fs", tier, duration)

    except Exception as exc:
        duration = round(time.monotonic() - started, 2)
        tb = traceback.format_exc()
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("Tier %d falhou: %s", tier, error_msg, exc_info=True)
        try:
            with SessionFactory() as session:
                session.add(
                    AutomationLog(
                        workflow=workflow,
                        tier=tier,
                        status="error",
                        signals_found=signals_found,
                        promos_new=promos_new,
                        emails_sent=emails_sent,
                        duration_seconds=duration,
                        error_message=error_msg[:2000],
                        error_traceback=tb[:5000],
                        gh_run_id=gh_run_id,
                    )
                )
                session.commit()
        except Exception:
            pass
        _send_slack_alert(tier, error_msg)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Radar de Milhas pipeline runner")
    parser.add_argument("--tier", type=int, choices=[1, 2], default=1, help="Monitor tier to run")
    args = parser.parse_args()
    main(args.tier)
