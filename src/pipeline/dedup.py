"""Deduplicação de promoções por fingerprint.

Fingerprint único para transferência: sha256(source_program + dest_program + bonus_pct + start_date)
Fingerprint único para acúmulo:       sha256(program + multiplier + trigger + start_date)

Múltiplos monitores capturando a mesma promo = 1 linha no DB.
"""

from __future__ import annotations

import logging
from typing import Any

from src.db.models import Promotion
from src.types import PromotionData

logger = logging.getLogger(__name__)


def find_existing(session: Any, fingerprint: str) -> Any | None:
    """Retorna o registro DB se o fingerprint já existe, None caso contrário."""
    return session.query(Promotion).filter_by(fingerprint=fingerprint).first()


def save_promotion(session: Any, promo: PromotionData) -> tuple[Any, bool]:
    """Persiste a promoção se ainda não existir. Retorna (model, is_new).

    is_new=False significa que a promo já estava no DB (dedup aplicado).
    """

    existing = find_existing(session, promo.fingerprint)
    if existing:
        logger.debug("Dedup: fingerprint %s já existe", promo.fingerprint[:12])
        return existing, False

    db_promo = Promotion(
        fingerprint=promo.fingerprint,
        source_program=promo.source_program,
        source_type=promo.source_type,
        source_url=promo.source_url,
        title=promo.title,
        promo_type=promo.promo_type,
        origin_program=promo.origin_program,
        destination_program=promo.destination_program,
        bonus_percent=promo.bonus_percent,
        starts_at=promo.starts_at,
        ends_at=promo.ends_at,
        conditions=promo.conditions,
        requires_club=promo.requires_club,
        requires_card=promo.requires_card,
        cpf_limit=promo.cpf_limit,
        confidence=promo.confidence,
        raw_data=promo.raw_data,
    )
    session.add(db_promo)
    session.flush()
    logger.info(
        "Nova promoção salva: %s (fp=%s)", promo.title or "sem título", promo.fingerprint[:12]
    )
    return db_promo, True


def dedup_batch(session: Any, promos: list[PromotionData]) -> list[tuple[Any, bool]]:
    """Processa um lote de promoções, desduplicando e salvando.

    Retorna lista de (model, is_new). Faz commit no final.
    """
    results: list[tuple[Any, bool]] = []
    for promo in promos:
        result = save_promotion(session, promo)
        results.append(result)
    session.commit()
    new_count = sum(1 for _, is_new in results if is_new)
    logger.info("Dedup batch: %d entrada(s), %d nova(s)", len(promos), new_count)
    return results
