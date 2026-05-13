"""Envia e-mails de teste com dados mock — confirmation e day1.

Usa as credenciais do .env sem tocar no banco ou dedup.

    py -3 scripts/send_test_email.py
    py -3 scripts/send_test_email.py --template confirmation
    py -3 scripts/send_test_email.py --template day1
    py -3 scripts/send_test_email.py --to outro@email.com
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level="INFO",
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("send_test_email")


# ---------------------------------------------------------------------------
# Dados mock
# ---------------------------------------------------------------------------


@dataclass
class MockPromo:
    id: str
    promo_type: str
    origin_program: str | None
    dest_program: str | None
    program: str | None
    bonus_percent: int
    ends_at: datetime
    title: str
    source_url: str


MOCK_TRANSFER_PROMOS = [
    MockPromo(
        id=str(uuid4()),
        promo_type="transfer_bonus",
        origin_program="Livelo",
        dest_program="Smiles",
        program=None,
        bonus_percent=100,
        ends_at=datetime.now(UTC) + timedelta(days=5),
        title="Livelo → Smiles com 100% de bônus",
        source_url="https://www.livelo.com.br",
    ),
    MockPromo(
        id=str(uuid4()),
        promo_type="transfer_bonus",
        origin_program="Esfera",
        dest_program="Azul",
        program=None,
        bonus_percent=80,
        ends_at=datetime.now(UTC) + timedelta(days=3),
        title="Esfera → Azul com 80% de bônus",
        source_url="https://www.esfera.com.vc",
    ),
]

MOCK_ACCUM_PROMOS = [
    MockPromo(
        id=str(uuid4()),
        promo_type="accumulation_bonus",
        origin_program=None,
        dest_program=None,
        program="LATAM Pass",
        bonus_percent=50,
        ends_at=datetime.now(UTC) + timedelta(days=7),
        title="LATAM Pass — acúmulo com 50% de bônus",
        source_url="https://www.latam.com",
    ),
]

MOCK_TRANSFER_PAIRS = [("Livelo", "Smiles"), ("Esfera", "Azul"), ("Livelo", "Azul")]
MOCK_ACCUM_PROGRAMS = ["Smiles", "LATAM Pass"]


@dataclass
class MockUser:
    name: str = "Felipe"
    monitored_programs: list[str] = None  # type: ignore[assignment]
    transfer_pairs: list[tuple[str, str]] = None  # type: ignore[assignment]
    unsubscribe_token: str = "test-token"

    def __post_init__(self) -> None:
        if self.monitored_programs is None:
            self.monitored_programs = MOCK_ACCUM_PROGRAMS
        if self.transfer_pairs is None:
            self.transfer_pairs = MOCK_TRANSFER_PAIRS


MOCK_USER = MockUser()


# ---------------------------------------------------------------------------
# Envio
# ---------------------------------------------------------------------------


def send(to: str, template: str) -> None:
    from src.config.settings import settings
    from src.pipeline.dispatcher import _render_template, send_email

    user_id = str(uuid4())
    unsubscribe_url = f"{settings.app_base_url}/api/unsubscribe/test-token"
    manage_url = f"{settings.app_base_url}/?user_id={user_id}"

    if template == "confirmation":
        html = _render_template(
            "confirmation.html",
            {
                "email_title": "[TEST] Preferências salvas — Radar de Milhas",
                "header_title": 'Prefer&ecirc;ncias <span style="color:#0891b2">Salvas</span>',
                "user": MOCK_USER,
                "transfer_pairs": MOCK_TRANSFER_PAIRS,
                "accumulation_programs": MOCK_ACCUM_PROGRAMS,
                "unsubscribe_url": unsubscribe_url,
                "manage_url": manage_url,
            },
        )
        subject = "[TEST] Radar de Milhas — Preferências salvas"

    else:  # day1
        html = _render_template(
            "day1.html",
            {
                "email_title": "[TEST] Promoções para Você — Radar de Milhas",
                "header_title": 'Promoções <span style="color:#0891b2">para Você</span>',
                "user": MOCK_USER,
                "transfer_promos": MOCK_TRANSFER_PROMOS,
                "accum_promos": MOCK_ACCUM_PROMOS,
                "unsubscribe_url": unsubscribe_url,
                "manage_url": manage_url,
            },
        )
        n = len(MOCK_TRANSFER_PROMOS) + len(MOCK_ACCUM_PROMOS)
        subject = f"[TEST] Radar de Milhas — {n} promoções pra você"

    log.info("Enviando template '%s' para %s …", template, to)
    ok = send_email(to, subject, html)
    if ok:
        log.info("E-mail enviado com sucesso.")
    else:
        log.error("Falha no envio — verifique as credenciais no .env.")
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    from src.config.settings import settings

    parser = argparse.ArgumentParser(description="Envia e-mail de teste com dados mock.")
    parser.add_argument(
        "--template",
        choices=["confirmation", "day1", "all"],
        default="all",
        help="Template a enviar (padrão: all)",
    )
    parser.add_argument(
        "--to",
        default=settings.digest_recipient,
        help=f"Destinatário (padrão: {settings.digest_recipient})",
    )
    args = parser.parse_args()

    templates = ["confirmation", "day1"] if args.template == "all" else [args.template]
    for tpl in templates:
        send(args.to, tpl)


if __name__ == "__main__":
    main()
