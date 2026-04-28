"""Tier 1 — Executa em todos os 6 scans diários (06,09,12,15,18,21 BRT).

Monitores: direct_scraper, hash_diff, rss_monitor, google_news.
Pipeline: RawSignal → extractor → dedup → preference_filter → dispatcher.
O scan das 12h sempre envia e-mail de rotina; demais enviam apenas se nova promo.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.config.settings import ACCUMULATION_PROGRAMS, VALID_TRANSFER_PAIRS
from src.pipeline.dedup import dedup_batch
from src.pipeline.extractor import extract
from src.pipeline.monitors.direct_scraper import scan_all_programs
from src.pipeline.monitors.google_news import scan_google_news
from src.pipeline.monitors.hash_diff import scan_hash_diff
from src.pipeline.monitors.news_scraper import scan_all_news
from src.pipeline.monitors.rss_monitor import scan_rss
from src.pipeline.preference_filter import load_all_preferences
from src.tools.user_agents import rotate_ua
from src.types import PromotionData, UserPreferencesData

logger = logging.getLogger(__name__)


def _is_relevant_promo(promo: PromotionData) -> bool:
    """Descarta promoções fora dos pares de transferência e programas de acúmulo monitorados."""
    if promo.promo_type == "transfer_bonus":
        origin = (promo.origin_program or promo.source_program or "").lower()
        dest = (promo.destination_program or "").lower()
        return (origin, dest) in VALID_TRANSFER_PAIRS
    program = (promo.origin_program or promo.source_program or "").lower()
    return program in ACCUMULATION_PROGRAMS


def _db_promo_matches_prefs(promo: Any, prefs: UserPreferencesData) -> bool:
    """Verifica se um registro Promotion do banco bate com as preferências do usuário."""
    if promo.promo_type == "transfer_bonus":
        if not prefs.transfer_pairs:
            return False
        origin = (promo.origin_program or promo.source_program or "").lower()
        dest = (promo.destination_program or "").lower()
        return any(p.source.lower() == origin and p.dest.lower() == dest for p in prefs.transfer_pairs)
    program = (promo.origin_program or promo.source_program or "").lower()
    return program in {p.lower() for p in prefs.accumulation_programs}


def run_tier1(
    session: Any,
    scheduler: Any | None = None,
    dry_run: bool = False,
    force_send: bool = False,
) -> list[PromotionData]:
    """Executa o pipeline completo Tier 1.

    Args:
        session: SQLAlchemy session.
        scheduler: instância APScheduler para agendamento de Dia 2/3.
        dry_run: se True, processa tudo mas não envia e-mails.
        force_send: se True, envia e-mail mesmo sem novas promoções (usado às 12h).

    Returns:
        lista de PromotionData novas detectadas neste scan.
    """
    rotate_ua()
    logger.info("=== Tier 1 scan iniciado ===")

    # News blogs first (primary source), then direct program scraping
    signals = []
    signals.extend(scan_rss())
    signals.extend(scan_google_news())
    signals.extend(scan_all_news())
    signals.extend(scan_hash_diff())
    signals.extend(scan_all_programs())

    logger.info("Tier 1: %d sinais coletados", len(signals))

    raw_promos: list[PromotionData] = []
    for signal in signals:
        raw_promos.extend(extract(signal))

    logger.info("Tier 1: %d promoções extraídas antes de dedup", len(raw_promos))

    raw_promos = [p for p in raw_promos if _is_relevant_promo(p)]
    logger.info("Tier 1: %d promoções após filtro de pares/programas válidos", len(raw_promos))

    if not raw_promos:
        logger.info("Tier 1: nenhuma promoção relevante extraída, encerrando")
        return []

    dedup_results = dedup_batch(session, raw_promos)
    new_promos_data = [data for data, is_new in dedup_results if is_new]
    logger.info("Tier 1: %d promoções novas após dedup", len(new_promos_data))

    if not new_promos_data and not force_send:
        logger.info("Tier 1: sem novas promoções e não é scan das 12h, sem e-mail")
        return []

    if dry_run:
        logger.info("[DRY RUN] Tier 1: pulando envio de e-mails")
        return new_promos_data

    _dispatch_emails(session, new_promos_data, scheduler)
    return new_promos_data


def _dispatch_emails(
    session: Any, new_promos_data: list[PromotionData], scheduler: Any | None
) -> None:
    from src.config.settings import settings as _settings
    from src.db.models import EmailLog, Promotion
    from src.pipeline.dispatcher import dispatch_day1, dispatch_upcoming

    now = datetime.now(UTC)
    all_prefs = load_all_preferences(session)

    if not all_prefs:
        logger.warning("Nenhuma preferência de usuário cadastrada, sem e-mails")
        return

    # All active promos in DB (ends_at required, started or no start date)
    all_active_db: list[Any] = (
        session.query(Promotion)
        .filter(
            Promotion.ends_at.isnot(None),
            Promotion.ends_at > now,
            Promotion.promo_type == "transfer_bonus",
            Promotion.bonus_percent.isnot(None),
            (Promotion.starts_at == None) | (Promotion.starts_at <= now),  # noqa: E711
        )
        .order_by(Promotion.bonus_percent.desc().nullslast())
        .all()
    )

    # Future promos: only newly discovered this scan
    new_fingerprints = {p.fingerprint for p in new_promos_data}
    new_db_promos: list[Any] = (
        session.query(Promotion).filter(Promotion.fingerprint.in_(new_fingerprints)).all()
        if new_fingerprints
        else []
    )
    future_db = [
        p for p in new_db_promos
        if p.starts_at is not None
        and p.starts_at > now
        and p.ends_at is not None
        and p.ends_at > now
        and p.promo_type == "transfer_bonus"
        and p.bonus_percent is not None
    ]

    for prefs in all_prefs:
        user_email = prefs.email or _settings.digest_recipient

        # Promos already sent to this user (day 1 is the only active-promo send)
        sent_ids = {
            str(row.promo_id)
            for row in session.query(EmailLog.promo_id)
            .filter(EmailLog.user_id == prefs.user_id, EmailLog.day_number == 1)
            .all()
        }

        # Active promos matching this user's preferences not yet received
        user_active = [
            p for p in all_active_db
            if str(p.id) not in sent_ids and _db_promo_matches_prefs(p, prefs)
        ]

        if user_active:
            dispatch_day1(
                session=session,
                user_id=prefs.user_id,
                user_email=user_email,
                new_promos=user_active,
                scheduler=scheduler,
                unsubscribe_token=prefs.unsubscribe_token,
            )

        # Future promos: only newly discovered ones for this user
        user_future = [
            p for p in future_db
            if str(p.id) not in sent_ids and _db_promo_matches_prefs(p, prefs)
        ]

        if user_future:
            dispatch_upcoming(
                session=session,
                user_id=prefs.user_id,
                user_email=user_email,
                future_promos=user_future,
                scheduler=scheduler,
                unsubscribe_token=prefs.unsubscribe_token,
            )
