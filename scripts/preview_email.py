"""Envia e-mail de preview com promoções fictícias para testar o design.

    py -3 scripts/preview_email.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config.settings import settings
from src.pipeline.dispatcher import _render_template, send_email

TO = settings.digest_recipient

now = datetime.now(UTC)


def _promo(**kwargs):
    defaults = dict(
        id="preview-001",
        title=None,
        promo_type="transfer_bonus",
        origin_program=None,
        source_program=None,
        destination_program=None,
        bonus_percent=None,
        starts_at=None,
        ends_at=now + timedelta(days=7),
        conditions=None,
        source_url="https://milhas.felipefinfanfa.com.br",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


transfer_promos = [
    _promo(
        title="Bônus de 100% na transferência Esfera → Smiles",
        promo_type="transfer_bonus",
        origin_program="esfera",
        source_program="esfera",
        destination_program="smiles",
        bonus_percent=100,
        starts_at=now,
        ends_at=now + timedelta(days=5),
        conditions="Mínimo de 1.000 pontos",
    ),
    _promo(
        title="Transferência Livelo → Azul com bônus de 60%",
        promo_type="transfer_bonus",
        origin_program="livelo",
        source_program="livelo",
        destination_program="azul",
        bonus_percent=60,
        starts_at=now + timedelta(days=1),
        ends_at=now + timedelta(days=10),
    ),
]

accum_promos = [
    _promo(
        title="Acúmulo em dobro no Smiles com cartão Nubank",
        promo_type="accumulation",
        source_program="smiles",
        origin_program="smiles",
        destination_program=None,
        bonus_percent=40,
        ends_at=now + timedelta(days=3),
        conditions="Válido para compras acima de R$ 300",
    ),
]

html = _render_template(
    "day1.html",
    {
        "email_title": "Preview do design — Radar de Milhas",
        "header_title": 'Promoções <span style="color:#0891b2">para Você</span>',
        "transfer_promos": transfer_promos,
        "accum_promos": accum_promos,
        "manage_url": f"{settings.app_base_url}/?user_id=preview",
        "unsubscribe_url": f"{settings.app_base_url}/preferences/unsubscribe/preview-token",
    },
)

n = len(transfer_promos) + len(accum_promos)
subject = f"Radar de Milhas — {n} promoções (preview de design)"

sent = send_email(TO, subject, html)
print(f"{'OK: E-mail enviado para ' + TO if sent else 'ERRO: Falha ao enviar'}")
