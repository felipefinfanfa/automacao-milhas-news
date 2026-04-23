"""Controle da sequência de 3 dias de e-mail por (promo_id, user_id).

- Dia 1: disparo imediato na primeira detecção confirmada.
- Dia 2: exatamente 24h após o Dia 1.
- Dia 3: exatamente 48h após o Dia 1.
- Nunca envia Dia 2/3 se promotion.valid_until < now().
- Prorrogação de promoção não reinicia a sequência.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from src.db.models import EmailLog

logger = logging.getLogger(__name__)


def has_sent(session: Any, user_id: str, promo_id: str, day_number: int) -> bool:
    """Verifica se o e-mail do dia X já foi enviado para este (user, promo)."""
    exists = (
        session.query(EmailLog)
        .filter_by(
            user_id=user_id,
            promo_id=promo_id,
            day_number=day_number,
        )
        .first()
    )
    return exists is not None


def record_sent(session: Any, user_id: str, promo_id: str, day_number: int) -> None:
    """Registra envio no email_log. Deve ser chamado após envio bem-sucedido."""
    log = EmailLog(
        user_id=user_id,
        promo_id=promo_id,
        day_number=day_number,
        sent_at=datetime.now(timezone.utc),
    )
    session.add(log)
    session.commit()
    logger.debug(
        "email_log registrado: user=%s promo=%s day=%d", user_id[:8], str(promo_id)[:8], day_number
    )


def get_day1_sent_at(session: Any, user_id: str, promo_id: str) -> datetime | None:
    """Retorna sent_at do Dia 1, ou None se ainda não enviado."""
    row = (
        session.query(EmailLog)
        .filter_by(user_id=user_id, promo_id=promo_id, day_number=1)
        .first()
    )
    return row.sent_at if row else None


def should_send_day(
    session: Any,
    user_id: str,
    promo_id: str,
    day_number: int,
    promo_ends_at: datetime | None,
) -> bool:
    """Decide se o e-mail do dia X deve ser enviado agora.

    Regras:
    - Dia 1: apenas se ainda não enviado.
    - Dia 2/3: apenas se Dia 1 foi enviado, intervalo atingido e promo ainda ativa.
    - Nunca envia se promo expirou.
    """
    now = datetime.now(timezone.utc)

    if promo_ends_at and promo_ends_at < now:
        logger.debug(
            "Promoção %s expirada, não envia Dia %d", str(promo_id)[:8], day_number
        )
        return False

    if has_sent(session, user_id, promo_id, day_number):
        return False

    if day_number == 1:
        return True

    day1_sent = get_day1_sent_at(session, user_id, promo_id)
    if day1_sent is None:
        return False

    required_delta = timedelta(hours=24 * (day_number - 1))
    return now >= day1_sent + required_delta


def schedule_followup_days(
    scheduler: Any,
    session: Any,
    user_id: str,
    promo_id: str,
    day1_sent_at: datetime,
    promo_ends_at: datetime | None,
    send_callback: Any,
) -> None:
    """Agenda Dia 2 e Dia 3 como jobs one-shot no APScheduler após o Dia 1."""
    for day_number in (2, 3):
        run_at = day1_sent_at + timedelta(hours=24 * (day_number - 1))

        if promo_ends_at and promo_ends_at < run_at:
            logger.info(
                "Dia %d não agendado para user=%s promo=%s: promo expira antes",
                day_number, user_id[:8], str(promo_id)[:8],
            )
            continue

        scheduler.add_job(
            send_callback,
            trigger="date",
            run_date=run_at,
            args=[user_id, promo_id, day_number],
            id=f"email_day{day_number}_{user_id}_{promo_id}",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(
            "Dia %d agendado para %s (user=%s promo=%s)",
            day_number, run_at.isoformat(), user_id[:8], str(promo_id)[:8],
        )
