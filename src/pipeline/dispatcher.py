"""Dispatcher de e-mail: decide se/quando enviar, consolida por usuário.

Provedor único: Resend.
Nunca envia e-mail vazio ou para promoção expirada.
Múltiplas promoções novas no mesmo scan = 1 e-mail consolidado por usuário.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from jinja2 import Environment, FileSystemLoader

from src.config.settings import settings
from src.db.models import EmailLog

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "email" / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)


# ---------------------------------------------------------------------------
# Email log helpers
# ---------------------------------------------------------------------------


def has_sent(session: Any, user_id: str, promo_id: str, day_number: int) -> bool:
    return (
        session.query(EmailLog)
        .filter_by(user_id=user_id, promo_id=promo_id, day_number=day_number)
        .first()
    ) is not None


def record_sent(session: Any, user_id: str, promo_id: str, day_number: int) -> None:
    session.add(
        EmailLog(
            user_id=user_id,
            promo_id=promo_id,
            day_number=day_number,
            sent_at=datetime.now(UTC),
        )
    )
    session.commit()
    logger.debug("email_log: user=%s promo=%s day=%d", user_id[:8], str(promo_id)[:8], day_number)


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


def _render_template(template_name: str, context: dict[str, Any]) -> str:
    now = datetime.now(UTC)
    context.setdefault("date_str", now.strftime("%A, %d de %B de %Y").lower())
    context.setdefault("unsubscribe_url", None)
    context.setdefault("manage_url", None)
    return _jinja_env.get_template(template_name).render(**context)


# ---------------------------------------------------------------------------
# Transport — Resend only
# ---------------------------------------------------------------------------


def send_email(to: str, subject: str, html: str) -> bool:
    if not settings.resend_api_key:
        logger.error("RESEND_API_KEY não configurada — e-mail não enviado")
        return False
    try:
        import resend

        resend.api_key = settings.resend_api_key
        resend.Emails.send(
            {
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "html": html,
            }
        )
        logger.info("E-mail enviado via Resend para %s", to)
        return True
    except Exception as exc:
        logger.error("Falha ao enviar via Resend para %s: %s", to, exc)
        return False


# ---------------------------------------------------------------------------
# Dispatch functions
# ---------------------------------------------------------------------------


def _build_email_urls(user_id: str, unsubscribe_token: str | None) -> tuple[str | None, str]:
    unsubscribe_url = (
        f"{settings.app_base_url}/api/unsubscribe/{unsubscribe_token}"
        if unsubscribe_token
        else None
    )
    manage_url = f"{settings.app_base_url}/?user_id={user_id}"
    return unsubscribe_url, manage_url


def dispatch_confirmation(
    user_id: str,
    user_email: str,
    unsubscribe_token: str | None,
    transfer_pairs: list[Any],
    accumulation_programs: list[str],
    flight_routes: list[Any] | None = None,
    flight_programs: list[str] | None = None,
    name: str | None = None,
) -> bool:
    unsubscribe_url, manage_url = _build_email_urls(user_id, unsubscribe_token)
    user = SimpleNamespace(
        name=name,
        monitored_programs=accumulation_programs,
        transfer_pairs=transfer_pairs,
        unsubscribe_token=unsubscribe_token,
    )
    html = _render_template(
        "confirmation.html",
        {
            "email_title": "Preferências salvas — Radar de Milhas",
            "header_title": 'Prefer&ecirc;ncias <span style="color:#0891b2">Salvas</span>',
            "user": user,
            "transfer_pairs": transfer_pairs,
            "accumulation_programs": accumulation_programs,
            "flight_routes": flight_routes or [],
            "flight_programs": flight_programs or [],
            "unsubscribe_url": unsubscribe_url,
            "manage_url": manage_url,
        },
    )
    sent = send_email(user_email, "Radar de Milhas — Preferências salvas", html)
    if sent:
        logger.info("Confirmação enviada para %s", user_email)
    return sent


def dispatch_day1(
    session: Any,
    user_id: str,
    user_email: str,
    new_promos: list[Any],
    unsubscribe_token: str | None = None,
    user_name: str | None = None,
) -> bool:
    now = datetime.now(UTC)

    promos_to_send = [
        p
        for p in new_promos
        if not has_sent(session, user_id, str(p.id), 1)
        and p.ends_at is not None
        and p.ends_at > now
    ]

    if not promos_to_send:
        return False

    sorted_promos = sorted(promos_to_send, key=lambda p: p.bonus_percent or 0, reverse=True)
    transfer_promos = [p for p in sorted_promos if p.promo_type == "transfer_bonus"]
    flight_promos = [p for p in sorted_promos if p.promo_type == "flight_award"]
    accum_promos = [
        p for p in sorted_promos if p.promo_type not in ("transfer_bonus", "flight_award")
    ]

    unsubscribe_url, manage_url = _build_email_urls(user_id, unsubscribe_token)

    html = _render_template(
        "day1.html",
        {
            "email_title": "Promoções para Você — Radar de Milhas",
            "header_title": 'Promoções <span style="color:#0891b2">para Você</span>',
            "user": {"name": user_name},
            "promotions": sorted_promos,
            "transfer_promos": transfer_promos,
            "flight_promos": flight_promos,
            "accum_promos": accum_promos,
            "unsubscribe_url": unsubscribe_url,
            "manage_url": manage_url,
        },
    )

    n = len(promos_to_send)
    subject = (
        f"Radar de Milhas — {n} nova{'s' if n > 1 else ''} "
        f"promoção{'ões' if n > 1 else ''} pra você"
    )
    sent = send_email(user_email, subject, html)

    if sent:
        for promo in promos_to_send:
            record_sent(session, user_id, str(promo.id), 1)

    return sent
