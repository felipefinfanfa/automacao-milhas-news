"""Tier 1 — HTML hash diff por URL monitorada.

Compara o SHA-256 do conteúdo atual com o hash armazenado em source_snapshots.
Emite sinal apenas quando há mudança, para evitar reprocessar conteúdo idêntico.
"""

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from src.config.settings import PROGRAM_URLS, settings
from src.tools.http_client import fetch
from src.types import RawSignal

logger = logging.getLogger(__name__)


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _get_snapshot(conn: Any, url: str) -> tuple[str | None, Any]:
    from sqlalchemy import text

    row = conn.execute(
        text("SELECT id, content_hash FROM source_snapshots WHERE url = :url"),
        {"url": url},
    ).first()
    if row:
        return str(row.content_hash), row.id
    return None, None


def _upsert_snapshot(conn: Any, url: str, content_hash: str, raw_content: str) -> None:
    from sqlalchemy import text

    conn.execute(
        text(
            """
            INSERT INTO source_snapshots (url, content_hash, raw_content, fetched_at)
            VALUES (:url, :hash, :content, NOW())
            ON CONFLICT (url) DO UPDATE
              SET content_hash = EXCLUDED.content_hash,
                  raw_content  = EXCLUDED.raw_content,
                  fetched_at   = EXCLUDED.fetched_at
            """
        ),
        {"url": url, "hash": content_hash, "content": raw_content[:50_000]},
    )


def scan_hash_diff(urls: dict[str, str] | None = None) -> list[RawSignal]:
    """Verifica se o conteúdo HTML de cada URL mudou desde o último scan.

    Args:
        urls: mapa {program_id: url} a monitorar. Default = PROGRAM_URLS.
    """
    if urls is None:
        urls = PROGRAM_URLS

    from src.db.models import create_engine_from_url

    engine = create_engine_from_url(settings.database_url)
    signals: list[RawSignal] = []

    for program, url in urls.items():
        try:
            content = fetch(url)
            new_hash = _sha256(content)

            with engine.begin() as conn:
                old_hash, _ = _get_snapshot(conn, url)
                changed = old_hash != new_hash
                _upsert_snapshot(conn, url, new_hash, content)

            if changed:
                logger.info("Hash diff detectado para %s (%s)", program, url)
                signals.append(
                    RawSignal(
                        source_url=url,
                        source_program=program,
                        source_type="hash_diff",
                        raw_content=content,
                        fetched_at=datetime.now(UTC),
                        extra={"new_hash": new_hash, "old_hash": old_hash},
                    )
                )
            else:
                logger.debug("Sem mudança para %s", program)

        except Exception as exc:
            logger.warning("Falha ao verificar hash diff de %s (%s): %s", program, url, exc)

    return signals
