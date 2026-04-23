"""Roda scan completo e envia e-mails para todos os usuários, ignorando dedup.

Uso único para testes — não registra nada no email_log.

    py -3 scripts/test_email.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level="INFO",
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)

# Força reenvio: has_sent() sempre retorna False e record_sent() não persiste nada
import src.email.sequence as _seq  # noqa: E402
_seq.has_sent = lambda *_: False          # type: ignore[assignment]
_seq.record_sent = lambda *_: None        # type: ignore[assignment]

from src.config.settings import settings  # noqa: E402
from src.db.models import create_engine_from_url, get_session_factory  # noqa: E402
from src.scheduler.jobs.tier1 import run_tier1  # noqa: E402

engine = create_engine_from_url(settings.database_url)
Session = get_session_factory(engine)

with Session() as session:
    new_promos = run_tier1(session, scheduler=None, dry_run=False, force_send=True)

logging.getLogger("test_email").info(
    "Scan concluído. %d promoção(ões) nova(s) detectada(s).", len(new_promos)
)
