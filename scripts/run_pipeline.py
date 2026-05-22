#!/usr/bin/env python3
"""Entry point for GitHub Actions: runs the full pipeline.

Usage:
    python scripts/run_pipeline.py
"""

from __future__ import annotations

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


def _send_slack_alert(error_msg: str) -> None:
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
            f"Run: <{run_url}|#{run_id}>\n"
            f"Error: {error_msg[:400]}"
        )
    }
    try:
        httpx.post(webhook, json=payload, timeout=10)
    except Exception:
        pass


def _run_monitors() -> list[Any]:
    from src.pipeline.monitors.news_monitor import scan_news

    rotate_ua()
    return scan_news()


def _is_relevant_promo(promo: PromotionData) -> bool:
    if promo.promo_type == "transfer_bonus":
        origin = (promo.origin_program or promo.source_program or "").lower()
        dest = (promo.destination_program or "").lower()
        return (origin, dest) in VALID_TRANSFER_PAIRS
    if promo.promo_type == "flight_award":
        return True
    program = (promo.origin_program or promo.source_program or "").lower()
    return program in ACCUMULATION_PROGRAMS


def _already_sent_semantic(promo: Any, sent_promos: list[Any]) -> bool:
    """True if user already received a semantically equivalent promotion."""
    for sp in sent_promos:
        if sp.promo_type != promo.promo_type:
            continue
        if promo.promo_type == "transfer_bonus":
            if (
                sp.origin_program == promo.origin_program
                and sp.destination_program == promo.destination_program
                and sp.bonus_percent == promo.bonus_percent
            ):
                return True
        elif promo.promo_type == "flight_award":
            if (
                sp.origin_iata == promo.origin_iata
                and sp.destination_iata == promo.destination_iata
            ):
                return True
    return False


def _db_promo_matches_prefs(promo: Any, prefs: UserPreferencesData) -> bool:
    if promo.promo_type == "transfer_bonus":
        if not prefs.transfer_pairs:
            return False
        origin = (promo.origin_program or promo.source_program or "").lower()
        dest = (promo.destination_program or "").lower()
        return any(
            p.source.lower() == origin and p.dest.lower() == dest for p in prefs.transfer_pairs
        )
    if promo.promo_type == "flight_award":
        from src.pipeline.preference_filter import _matches_flight_award

        return _matches_flight_award(promo, prefs)
    program = (promo.origin_program or promo.source_program or "").lower()
    return program in {p.lower() for p in prefs.accumulation_programs}


def _dispatch_emails(session: Any) -> int:
    now = datetime.now(UTC)
    all_prefs = load_all_preferences(session)

    if not all_prefs:
        logger.warning("Nenhuma preferência cadastrada — sem e-mails")
        return 0

    all_active_db: list[Any] = (
        session.query(Promotion)
        .filter(
            Promotion.ends_at.isnot(None),
            Promotion.ends_at > now,
            (Promotion.starts_at == None) | (Promotion.starts_at <= now),  # noqa: E711
        )
        .order_by(Promotion.bonus_percent.desc().nullslast())
        .all()
    )

    emails_sent = 0
    for prefs in all_prefs:
        user_email = prefs.email or settings.digest_recipient

        sent_rows = (
            session.query(EmailLog.promo_id)
            .filter(EmailLog.user_id == prefs.user_id, EmailLog.day_number == 1)
            .all()
        )
        sent_ids = {str(row.promo_id) for row in sent_rows}

        # Load full details of sent promos for semantic dedup comparison
        sent_promos = (
            session.query(Promotion)
            .filter(Promotion.id.in_([row.promo_id for row in sent_rows]))
            .all()
            if sent_rows
            else []
        )

        user_active = [
            p
            for p in all_active_db
            if str(p.id) not in sent_ids
            and not _already_sent_semantic(p, sent_promos)
            and _db_promo_matches_prefs(p, prefs)
        ]

        if user_active:
            sent = dispatch_day1(
                session=session,
                user_id=prefs.user_id,
                user_email=user_email,
                new_promos=user_active,
                unsubscribe_token=prefs.unsubscribe_token,
                user_name=prefs.name,
            )
            if sent:
                emails_sent += 1

    return emails_sent


def main() -> None:
    started = time.monotonic()
    engine = create_engine_from_url(settings.database_url)
    SessionFactory = get_session_factory(engine)
    gh_run_id = os.getenv("GITHUB_RUN_ID")

    signals_found = promos_new = emails_sent = 0

    try:
        signals = _run_monitors()
        signals_found = len(signals)
        logger.info("%d sinais coletados", signals_found)

        raw_promos: list[PromotionData] = []
        for signal in signals:
            raw_promos.extend(extract(signal))
        raw_promos = [p for p in raw_promos if _is_relevant_promo(p)]
        logger.info("%d promoções relevantes extraídas", len(raw_promos))

        with SessionFactory() as session:
            dedup_results = dedup_batch(session, raw_promos) if raw_promos else []
            promos_new = sum(1 for _, is_new in dedup_results if is_new)
            logger.info("%d promoções novas após dedup", promos_new)

            emails_sent = _dispatch_emails(session)
            logger.info("%d e-mails enviados", emails_sent)

        duration = round(time.monotonic() - started, 2)
        with SessionFactory() as session:
            session.add(
                AutomationLog(
                    workflow="pipeline",
                    tier=1,
                    status="success",
                    signals_found=signals_found,
                    promos_new=promos_new,
                    emails_sent=emails_sent,
                    duration_seconds=duration,
                    gh_run_id=gh_run_id,
                )
            )
            session.commit()
        logger.info("Pipeline completo em %.1fs", duration)

    except Exception as exc:
        duration = round(time.monotonic() - started, 2)
        tb = traceback.format_exc()
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("Pipeline falhou: %s", error_msg, exc_info=True)
        try:
            with SessionFactory() as session:
                session.add(
                    AutomationLog(
                        workflow="pipeline",
                        tier=1,
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
        _send_slack_alert(error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
