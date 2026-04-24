"""Filtra promoções pelas preferências do usuário.

Par de transferência é ordenado e não-comutativo: Esfera→Smiles ≠ Smiles→Esfera.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from src.types import PromotionData, TransferPair, UserPreferencesData

logger = logging.getLogger(__name__)


def matches_preferences(promo: PromotionData, prefs: UserPreferencesData) -> bool:
    """Retorna True se a promo bate com alguma preferência do usuário."""
    if promo.promo_type == "transfer_bonus":
        return _matches_transfer(promo, prefs)
    return _matches_accumulation(promo, prefs)


def _matches_transfer(promo: PromotionData, prefs: UserPreferencesData) -> bool:
    if not prefs.transfer_pairs:
        return False
    origin = (promo.origin_program or promo.source_program or "").lower()
    dest = (promo.destination_program or "").lower()
    for pair in prefs.transfer_pairs:
        if pair.source.lower() == origin and pair.dest.lower() == dest:
            return True
    return False


def _matches_accumulation(promo: PromotionData, prefs: UserPreferencesData) -> bool:
    if not prefs.accumulation_programs:
        return False
    program = (promo.origin_program or promo.source_program or "").lower()
    return program in [p.lower() for p in prefs.accumulation_programs]


def filter_for_user(
    promos: list[PromotionData],
    prefs: UserPreferencesData,
) -> list[PromotionData]:
    """Retorna somente as promoções ativas que batem com as preferências do usuário."""
    now = datetime.now(timezone.utc)
    active = [p for p in promos if p.ends_at is None or p.ends_at > now]
    matched = [p for p in active if matches_preferences(p, prefs)]
    logger.debug(
        "preference_filter user=%s: %d/%d promos passaram (%d expiradas descartadas)",
        str(prefs.user_id)[:8],
        len(matched),
        len(promos),
        len(promos) - len(active),
    )
    return matched


def filter_for_all_users(
    promos: list[PromotionData],
    all_prefs: list[UserPreferencesData],
) -> dict[str, list[PromotionData]]:
    """Retorna mapa {user_id: [promos filtradas]} para todos os usuários."""
    return {
        prefs.user_id: filter_for_user(promos, prefs)
        for prefs in all_prefs
    }


def load_all_preferences(session: Any) -> list[UserPreferencesData]:
    """Carrega preferências de todos os usuários do banco."""
    from src.db.models import UserPreferences

    rows = session.query(UserPreferences).all()
    result: list[UserPreferencesData] = []
    for row in rows:
        if not row.user_id:
            continue
        pairs = [
            TransferPair(source=p["source"], dest=p["dest"])
            for p in (row.transfer_pairs or [])
            if "source" in p and "dest" in p
        ]
        result.append(
            UserPreferencesData(
                user_id=str(row.user_id),
                email=row.email,
                name=row.name,
                phone=row.phone,
                unsubscribe_token=(
                    str(row.unsubscribe_token) if row.unsubscribe_token else None
                ),
                monitored_programs=row.monitored_programs or [],
                transfer_pairs=pairs,
                accumulation_programs=row.accumulation_programs or [],
            )
        )
    return result
