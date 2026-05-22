"""Deduplicação de promoções por fingerprint + verificação semântica.

Múltiplos monitores/artigos capturando a mesma promo = 1 linha no DB.
Dois níveis:
  1. Fingerprint SHA-256 (exato)
  2. Semântico: mesmo tipo + programas + bônus + mês de expiração
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.db.models import Promotion
from src.types import PromotionData

logger = logging.getLogger(__name__)


def find_existing(session: Any, fingerprint: str) -> Any | None:
    return session.query(Promotion).filter_by(fingerprint=fingerprint).first()


def _find_semantic_duplicate(session: Any, promo: PromotionData) -> Any | None:
    """Retorna promoção ativa semanticamente idêntica, independente do fingerprint.

    Evita duplicatas quando o mesmo artigo gera fingerprints ligeiramente diferentes
    por variação na extração (bônus ±5%, miles_count ligeiramente diferente, etc.).
    """
    now = datetime.now(UTC)

    if promo.promo_type == "transfer_bonus":
        if not promo.origin_program or not promo.destination_program:
            return None
        q = session.query(Promotion).filter(
            Promotion.promo_type == "transfer_bonus",
            Promotion.ends_at > now,
            Promotion.origin_program == promo.origin_program,
            Promotion.destination_program == promo.destination_program,
        )
        # Tolerância de ±5% no bônus para absorver ruído de extração
        # (e.g. "100% até 105%" pode virar 100 ou 105 dependendo do artigo).
        if promo.bonus_percent is not None:
            q = q.filter(
                Promotion.bonus_percent.between(
                    promo.bonus_percent - 5,
                    promo.bonus_percent + 5,
                )
            )
        return q.first()

    if promo.promo_type == "flight_award":
        # Match liberal: mesmo destino + (origem igual OU uma das duas é NULL).
        # Permite deduplicar artigos onde um extraiu "de São Paulo" e outro não.
        if not promo.destination_iata:
            return None
        q = session.query(Promotion).filter(
            Promotion.promo_type == "flight_award",
            Promotion.ends_at > now,
            Promotion.destination_iata == promo.destination_iata,
        )
        if promo.origin_iata:
            q = q.filter(
                (Promotion.origin_iata == promo.origin_iata) | (Promotion.origin_iata.is_(None))
            )
        return q.first()

    return None


def save_promotion(session: Any, promo: PromotionData) -> tuple[Any, bool]:
    """Persiste a promoção se não existir por fingerprint nem semanticamente.

    Retorna (model, is_new). is_new=False = dedup aplicado.
    """
    existing = find_existing(session, promo.fingerprint)
    if existing:
        logger.debug("Dedup fingerprint: %s", promo.fingerprint[:12])
        return existing, False

    semantic = _find_semantic_duplicate(session, promo)
    if semantic:
        logger.debug(
            "Dedup semântico: %s %s→%s já existe (id=%s)",
            promo.promo_type,
            promo.origin_program,
            promo.destination_program,
            str(semantic.id)[:8],
        )
        return semantic, False

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
        origin_iata=promo.origin_iata,
        destination_iata=promo.destination_iata,
        miles_count=promo.miles_count,
        raw_data=promo.raw_data,
    )
    session.add(db_promo)
    session.flush()
    logger.info("Nova promoção: %s (fp=%s)", promo.title or "sem título", promo.fingerprint[:12])
    return db_promo, True


def dedup_batch(session: Any, promos: list[PromotionData]) -> list[tuple[Any, bool]]:
    results: list[tuple[Any, bool]] = []
    for promo in promos:
        results.append(save_promotion(session, promo))
    session.commit()
    new_count = sum(1 for _, is_new in results if is_new)
    logger.info("Dedup batch: %d entrada(s), %d nova(s)", len(promos), new_count)
    return results
