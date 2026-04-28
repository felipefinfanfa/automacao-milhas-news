"""Reprocessa sinais históricos do banco.

OBRIGATÓRIO: sempre usar --dry-run primeiro.
Nunca apagar registros de email_log (histórico de auditoria).

Uso:
    python scripts/backfill_promos.py --dry-run
    python scripts/backfill_promos.py --since 2026-01-01
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill de promoções históricas")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        required=True,
        help="Simula o backfill sem gravar no banco",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Data de início do backfill (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Máximo de snapshots a reprocessar (default: 500)",
    )
    args = parser.parse_args()

    if not args.dry_run:
        logger.error("NUNCA rode backfill sem --dry-run. Abortando.")
        sys.exit(1)

    from src.config.settings import settings
    from src.db.models import SourceSnapshot, create_engine_from_url, get_session_factory
    from src.pipeline.extractor import extract
    from src.types import RawSignal

    engine = create_engine_from_url(settings.database_url)
    SessionFactory = get_session_factory(engine)

    since: datetime | None = None
    if args.since:
        since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=UTC)

    with SessionFactory() as session:
        query = session.query(SourceSnapshot)
        if since:
            query = query.filter(SourceSnapshot.fetched_at >= since)
        snapshots = query.order_by(SourceSnapshot.fetched_at.desc()).limit(args.limit).all()

        logger.info("[DRY RUN] Reprocessando %d snapshots", len(snapshots))

        total_extracted = 0
        total_would_create = 0

        for snap in snapshots:
            if not snap.raw_content:
                continue

            signal = RawSignal(
                source_url=snap.url,
                source_program=None,
                source_type="hash_diff",
                raw_content=snap.raw_content,
                fetched_at=snap.fetched_at,
            )
            promos = extract(signal)
            total_extracted += len(promos)

            for promo in promos:
                from src.pipeline.dedup import find_existing

                existing = find_existing(session, promo.fingerprint)
                if not existing:
                    total_would_create += 1
                    logger.info(
                        "[DRY RUN] Criaria: %s (%s→%s, %.0f%%)",
                        promo.title or "sem título",
                        promo.origin_program or "?",
                        promo.destination_program or "?",
                        promo.bonus_percent or 0,
                    )

        logger.info(
            "[DRY RUN] Resultado: %d promoções extraídas, %d novas seriam criadas",
            total_extracted,
            total_would_create,
        )


if __name__ == "__main__":
    main()
