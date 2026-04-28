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
from typing import Any

from jinja2 import Environment, FileSystemLoader

from src.config.settings import settings
from src.pipeline.sequence import has_sent, record_sent

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "email" / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)


def _render_template(template_name: str, context: dict[str, Any]) -> str:
    now = datetime.now(UTC)
    context.setdefault("date_str", now.strftime("%A, %d de %B de %Y").lower())
    context.setdefault("unsubscribe_url", None)
    context.setdefault("manage_url", None)
    tpl = _jinja_env.get_template(template_name)
    return tpl.render(**context)


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
    """Tenta Resend primeiro, cai para Gmail SMTP se falhar."""
    return _send_via_resend(to, subject, html) or _send_via_gmail(to, subject, html)


def dispatch_confirmation(
    user_id: str,
    user_email: str,
    unsubscribe_token: str | None,
    transfer_pairs: list[Any],
    accumulation_programs: list[str],
) -> bool:
    """Envia e-mail de confirmação após o usuário salvar suas preferências."""
    unsubscribe_url, manage_url = _build_email_urls(user_id, unsubscribe_token)
    html = _render_template(
        "confirmation.html",
        {
            "email_title": "Preferências salvas — Radar de Milhas",
            "header_title": 'Prefer&ecirc;ncias <span style="color:#0891b2">Salvas</span>',
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


def _build_email_urls(user_id: str, unsubscribe_token: str | None) -> tuple[str | None, str]:
    unsubscribe_url = (
        f"{settings.app_base_url}/preferences/unsubscribe/{unsubscribe_token}"
        if unsubscribe_token
        else None
    )
    manage_url = f"{settings.app_base_url}/?user_id={user_id}"
    return unsubscribe_url, manage_url


def dispatch_day1(
    session: Any,
    user_id: str,
    user_email: str,
    new_promos: list[Any],
    scheduler: Any | None = None,
    unsubscribe_token: str | None = None,
) -> bool:
    """Envia e-mail consolidado do Dia 1 para um usuário.

    Args:
        new_promos: promoções ativas não enviadas para este usuário (já filtradas por preferência).
        scheduler: ignorado — mantido por compatibilidade de assinatura.
        unsubscribe_token: token UUID do usuário para o link de cancelamento.

    Returns:
        True se o e-mail foi enviado com sucesso.
    """
    now = datetime.now(UTC)

    promos_to_send = [
        p
        for p in new_promos
        if not has_sent(session, user_id, str(p.id), 1) and p.ends_at is not None and p.ends_at > now
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
    subject = f"Radar de Milhas — {n} nova{'s' if n > 1 else ''} promoção{'ões' if n > 1 else ''} pra você"
    sent = send_email(user_email, subject, html)

    if sent:
        for promo in promos_to_send:
            record_sent(session, user_id, str(promo.id), 1)

    return sent


def _send_followup_day(user_id: str, promo_id: str, day_number: int) -> None:
    """Callback chamado pelo APScheduler para Dia 2 ou Dia 3.

    DEPRECATED — Não é mais agendado. Cada promoção é enviada exatamente 1 vez
    (day_number=1 apenas). Mantido caso jobs antigos ainda estejam na fila.
    """
    from src.config.settings import settings
    from src.db.models import (
        Promotion,
        UserPreferences,
        create_engine_from_url,
        get_session_factory,
    )

    engine = create_engine_from_url(settings.database_url)
    SessionFactory = get_session_factory(engine)

    with SessionFactory() as session:
        promo = session.query(Promotion).filter_by(id=promo_id).first()
        user_pref = session.query(UserPreferences).filter_by(user_id=user_id).first()

        if not promo or not user_pref:
            return

        now = datetime.now(UTC)
        if promo.ends_at and promo.ends_at < now:
            logger.info("Dia %d cancelado: promo %s expirada", day_number, promo_id[:8])
            return

        if has_sent(session, user_id, promo_id, day_number):
            return

        token = str(user_pref.unsubscribe_token) if user_pref.unsubscribe_token else None
        unsubscribe_url, manage_url = _build_email_urls(user_id, token)

        transfer_promos = [promo] if promo.promo_type == "transfer_bonus" else []
        accum_promos = [promo] if promo.promo_type != "transfer_bonus" else []
        html = _render_template(
            "day1.html",
            {
                "email_title": "Lembrete — Radar de Milhas",
                "header_title": 'Ainda <span style="color:#0891b2">Ativa</span>',
                "transfer_promos": transfer_promos,
                "accum_promos": accum_promos,
                "unsubscribe_url": unsubscribe_url,
                "manage_url": manage_url,
            },
        )

        user_email = user_pref.email or settings.digest_recipient
        subject = f"Radar de Milhas — Lembrete Dia {day_number}: promoção ainda ativa"
        sent = send_email(user_email, subject, html)

        if sent:
            record_sent(session, user_id, promo_id, day_number)


def dispatch_upcoming(
    session: Any,
    user_id: str,
    user_email: str,
    future_promos: list[Any],
    scheduler: Any | None = None,
    unsubscribe_token: str | None = None,
) -> bool:
    """Envia alerta de promoções futuras e agenda lembrete 24h antes de ativarem.

    Usa day_number=1 para o alerta no dia encontrado e day_number=2 para o
    lembrete pré-ativação. Nunca usa schedule_followup_days (sequência de 3 dias).
    """
    promos_to_send = [p for p in future_promos if not has_sent(session, user_id, str(p.id), 1)]

    if not promos_to_send:
        logger.debug("Nenhuma promo futura nova para user=%s", user_id[:8])
        return False

    sorted_upcoming = sorted(promos_to_send, key=lambda p: p.bonus_percent or 0, reverse=True)
    transfer_promos = [p for p in sorted_upcoming if p.promo_type == "transfer_bonus"]
    accum_promos = [p for p in sorted_upcoming if p.promo_type != "transfer_bonus"]

    unsubscribe_url, manage_url = _build_email_urls(user_id, unsubscribe_token)

    html = _render_template(
        "day1.html",
        {
            "email_title": "Em Breve — Radar de Milhas",
            "header_title": 'Chegando <span style="color:#0891b2">em Breve</span>',
            "transfer_promos": transfer_promos,
            "accum_promos": accum_promos,
            "unsubscribe_url": unsubscribe_url,
            "manage_url": manage_url,
        },
    )

    n = len(promos_to_send)
    subject = f"Radar de Milhas — {n} promoção{'ões' if n > 1 else ''} chegando em breve"
    sent = send_email(user_email, subject, html)

    if sent:
        for promo in promos_to_send:
            record_sent(session, user_id, str(promo.id), 1)
            if scheduler and promo.starts_at:
                _schedule_pre_activation_reminder(
                    scheduler=scheduler,
                    user_id=user_id,
                    promo_id=str(promo.id),
                    starts_at=promo.starts_at,
                )

    return sent


def _schedule_pre_activation_reminder(
    scheduler: Any,
    user_id: str,
    promo_id: str,
    starts_at: datetime,
) -> None:
    """Agenda lembrete 24h antes de uma promoção futura entrar em vigor."""
    from datetime import timedelta

    reminder_at = starts_at - timedelta(hours=24)
    now = datetime.now(UTC)

    if reminder_at <= now:
        logger.info(
            "Lembrete pré-ativação ignorado: menos de 24h até início (promo=%s)", promo_id[:8]
        )
        return

    job_id = f"upcoming_reminder_{user_id}_{promo_id}"
    scheduler.add_job(
        _send_pre_activation_reminder,
        trigger="date",
        run_date=reminder_at,
        args=[user_id, promo_id],
        id=job_id,
        replace_existing=True,
        misfire_grace_time=3600,
    )
    logger.info(
        "Lembrete pré-ativação agendado para %s (user=%s promo=%s)",
        reminder_at.isoformat(),
        user_id[:8],
        promo_id[:8],
    )


def _send_pre_activation_reminder(user_id: str, promo_id: str) -> None:
    """Callback APScheduler: envia lembrete 24h antes de promoção futura ativar."""
    from src.config.settings import settings
    from src.db.models import (
        Promotion,
        UserPreferences,
        create_engine_from_url,
        get_session_factory,
    )

    engine = create_engine_from_url(settings.database_url)
    SessionFactory = get_session_factory(engine)

    with SessionFactory() as session:
        promo = session.query(Promotion).filter_by(id=promo_id).first()
        user_pref = session.query(UserPreferences).filter_by(user_id=user_id).first()

        if not promo or not user_pref:
            return

        if has_sent(session, user_id, promo_id, 2):
            return

        token = str(user_pref.unsubscribe_token) if user_pref.unsubscribe_token else None
        unsubscribe_url, manage_url = _build_email_urls(user_id, token)
        user_email = user_pref.email or settings.digest_recipient

        transfer_promos = [promo] if promo.promo_type == "transfer_bonus" else []
        accum_promos = [promo] if promo.promo_type != "transfer_bonus" else []
        html = _render_template(
            "day1.html",
            {
                "email_title": "Começa Amanhã — Radar de Milhas",
                "header_title": 'Começa <span style="color:#0891b2">Amanhã</span>',
                "transfer_promos": transfer_promos,
                "accum_promos": accum_promos,
                "unsubscribe_url": unsubscribe_url,
                "manage_url": manage_url,
            },
        )

        subject = "Radar de Milhas — Promoção começa amanhã!"
        sent = send_email(user_email, subject, html)

        if sent:
            record_sent(session, user_id, promo_id, 2)
