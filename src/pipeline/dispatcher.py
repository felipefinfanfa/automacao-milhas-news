"""Dispatcher de e-mail: decide se/quando enviar, consolida por usuário.

Prioridade de envio: Resend (primary) → Gmail SMTP (fallback).
Nunca envia e-mail vazio ou para promoção expirada.
Múltiplas promoções novas no mesmo scan = 1 e-mail consolidado por usuário.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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
# Email log helpers (inlined from the deleted sequence.py)
# ---------------------------------------------------------------------------


def has_sent(session: Any, user_id: str, promo_id: str, day_number: int) -> bool:
    """Returns True if the email for day N was already sent for this (user, promo)."""
    return (
        session.query(EmailLog)
        .filter_by(user_id=user_id, promo_id=promo_id, day_number=day_number)
        .first()
    ) is not None


def record_sent(session: Any, user_id: str, promo_id: str, day_number: int) -> None:
    """Records a successful send in email_log. Call only after a confirmed send."""
    log = EmailLog(
        user_id=user_id,
        promo_id=promo_id,
        day_number=day_number,
        sent_at=datetime.now(UTC),
    )
    session.add(log)
    session.commit()
    logger.debug(
        "email_log registrado: user=%s promo=%s day=%d",
        user_id[:8],
        str(promo_id)[:8],
        day_number,
    )


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


def _render_template(template_name: str, context: dict[str, Any]) -> str:
    now = datetime.now(UTC)
    context.setdefault("date_str", now.strftime("%A, %d de %B de %Y").lower())
    context.setdefault("unsubscribe_url", None)
    context.setdefault("manage_url", None)
    tpl = _jinja_env.get_template(template_name)
    return tpl.render(**context)


# ---------------------------------------------------------------------------
# Transport layer
# ---------------------------------------------------------------------------


def _send_via_resend(to: str, subject: str, html: str) -> bool:
    if not settings.resend_api_key:
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
        logger.warning("Falha ao enviar via Resend: %s", exc)
        return False


def _send_via_gmail(to: str, subject: str, html: str) -> bool:
    if not settings.gmail_user or not settings.gmail_app_password:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.gmail_user
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.gmail_user, settings.gmail_app_password)
            server.sendmail(settings.gmail_user, [to], msg.as_string())
        logger.info("E-mail enviado via Gmail SMTP para %s", to)
        return True
    except Exception as exc:
        logger.error("Falha ao enviar via Gmail: %s", exc)
        return False


def send_email(to: str, subject: str, html: str) -> bool:
    """Tries Resend first, falls back to Gmail SMTP."""
    return _send_via_resend(to, subject, html) or _send_via_gmail(to, subject, html)


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
    name: str | None = None,
) -> bool:
    """Sends confirmation email after user saves preferences."""
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
            "unsubscribe_url": unsubscribe_url,
            "manage_url": manage_url,
        },
    )
    sent = send_email(user_email, "Radar de Milhas — Preferências salvas", html)
    if sent:
        logger.info("E-mail de confirmação enviado para %s", user_email)
    return sent


def dispatch_day1(
    session: Any,
    user_id: str,
    user_email: str,
    new_promos: list[Any],
    unsubscribe_token: str | None = None,
) -> bool:
    """Sends consolidated Day 1 email to a user.

    Args:
        new_promos: active promos not yet sent to this user (already preference-filtered).

    Returns:
        True if the email was sent successfully.
    """
    now = datetime.now(UTC)

    promos_to_send = [
        p
        for p in new_promos
        if not has_sent(session, user_id, str(p.id), 1)
        and p.ends_at is not None
        and p.ends_at > now
    ]

    if not promos_to_send:
        logger.debug("Nenhuma promo nova para user=%s", user_id[:8])
        return False

    sorted_promos = sorted(promos_to_send, key=lambda p: p.bonus_percent or 0, reverse=True)
    transfer_promos = [p for p in sorted_promos if p.promo_type == "transfer_bonus"]
    accum_promos = [p for p in sorted_promos if p.promo_type != "transfer_bonus"]

    unsubscribe_url, manage_url = _build_email_urls(user_id, unsubscribe_token)

    html = _render_template(
        "day1.html",
        {
            "email_title": "Promoções para Você — Radar de Milhas",
            "header_title": 'Promoções <span style="color:#0891b2">para Você</span>',
            "transfer_promos": transfer_promos,
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
