"""Tier 1 — Executa em todos os 6 scans diários (06,09,12,15,18,21 BRT).

Monitores: direct_scraper, hash_diff, rss_monitor, google_news.
Pipeline: RawSignal → extractor → dedup → preference_filter → dispatcher.
O scan das 12h sempre envia e-mail de rotina; demais enviam apenas se nova promo.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.integrations.user_agents import rotate_ua
from src.monitors.direct_scraper import scan_all_programs
from src.monitors.google_news import scan_google_news
from src.monitors.hash_diff import scan_hash_diff
from src.monitors.rss_monitor import scan_rss
from src.processor.dedup import dedup_batch
from src.processor.extractor import extract
from src.processor.preference_filter import filter_for_all_users, load_all_preferences
from src.types import PromotionData

logger = logging.getLogger(__name__)


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

    signals = []
    signals.extend(scan_rss())
    signals.extend(scan_google_news())
    signals.extend(scan_hash_diff())
    signals.extend(scan_all_programs())

    logger.info("Tier 1: %d sinais coletados", len(signals))

    raw_promos: list[PromotionData] = []
    for signal in signals:
        raw_promos.extend(extract(signal))

    logger.info("Tier 1: %d promoções extraídas antes de dedup", len(raw_promos))

    if not raw_promos:
        logger.info("Tier 1: nenhuma promoção extraída, encerrando")
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


def _dispatch_emails(session: Any, new_promos_data: list[PromotionData], scheduler: Any | None) -> None:
    from src.config.settings import settings as _settings
    from src.db.models import Promotion
    from src.email.dispatcher import dispatch_day1, dispatch_upcoming

    now = datetime.now(timezone.utc)
    all_prefs = load_all_preferences(session)

    if not all_prefs:
        logger.warning("Nenhuma preferência de usuário cadastrada, sem e-mails")
        return

    new_fingerprints = {p.fingerprint for p in new_promos_data}
    new_db_promos = (
        session.query(Promotion)
        .filter(Promotion.fingerprint.in_(new_fingerprints))
        .all()
    )

    # Descarta promoções expiradas
    new_db_promos = [
        p for p in new_db_promos
        if p.ends_at is None or p.ends_at > now
    ]

    # Mantém apenas transferências bonificadas com % definido
    new_db_promos = [
        p for p in new_db_promos
        if p.promo_type == "transfer_bonus" and p.bonus_percent is not None
    ]

    # Separa ativas (starts_at <= now ou sem data de início) das futuras
    active_db = [p for p in new_db_promos if p.starts_at is None or p.starts_at <= now]
    future_db = [p for p in new_db_promos if p.starts_at is not None and p.starts_at > now]

    # Top 20 transferências bonificadas ativas do banco para o digest consolidado
    active_promos = (
        session.query(Promotion)
        .filter(
            (Promotion.ends_at == None) | (Promotion.ends_at > now),  # noqa: E711
            (Promotion.starts_at == None) | (Promotion.starts_at <= now),  # noqa: E711
            Promotion.promo_type == "transfer_bonus",
            Promotion.bonus_percent.isnot(None),
        )
        .order_by(Promotion.bonus_percent.desc().nullslast())
        .limit(20)
        .all()
    )

    for_users = filter_for_all_users(new_promos_data, all_prefs)

    for prefs in all_prefs:
        user_new = for_users.get(prefs.user_id, [])
        if not user_new:
            continue

        user_fingerprints = {p.fingerprint for p in user_new}
        user_active_db = [p for p in active_db if p.fingerprint in user_fingerprints]
        user_future_db = [p for p in future_db if p.fingerprint in user_fingerprints]
        user_email = prefs.email or _settings.digest_recipient

        if user_active_db:
            dispatch_day1(
                session=session,
                user_id=prefs.user_id,
                user_email=user_email,
                new_promos=user_active_db,
                all_active_promos=active_promos,
                scheduler=scheduler,
                unsubscribe_token=prefs.unsubscribe_token,
            )

        if user_future_db:
            dispatch_upcoming(
                session=session,
                user_id=prefs.user_id,
                user_email=user_email,
                future_promos=user_future_db,
                scheduler=scheduler,
                unsubscribe_token=prefs.unsubscribe_token,
            )
