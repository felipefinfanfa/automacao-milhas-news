"""Filtra promoções pelas preferências do usuário.

Par de transferência é ordenado e não-comutativo: Esfera→Smiles ≠ Smiles→Esfera.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.types import FlightRoute, PromotionData, TransferPair, UserPreferencesData

logger = logging.getLogger(__name__)


def matches_preferences(promo: PromotionData, prefs: UserPreferencesData) -> bool:
    """Retorna True se a promo bate com alguma preferência do usuário."""
    if promo.promo_type == "transfer_bonus":
        return _matches_transfer(promo, prefs)
    if promo.promo_type == "flight_award":
        return _matches_flight_award(promo, prefs)
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


def _matches_flight_award(promo: PromotionData, prefs: UserPreferencesData) -> bool:
    if not prefs.flight_routes and not prefs.flight_programs:
        return False

    # Artigos RSS têm source_program="unknown"; o programa real fica em origin_program
    if prefs.flight_programs:
        prog = (promo.origin_program or promo.source_program or "").lower()
        if prog not in [p.lower() for p in prefs.flight_programs]:
            return False

    # Sem rotas configuradas → qualquer rota do programa aceito basta
    if not prefs.flight_routes:
        return True

    # Cada FlightRoute é um filtro OR independente
    for route in prefs.flight_routes:
        origin_ok = route.origin_iata is None or route.origin_iata == promo.origin_iata
        dest_ok = route.destination_iata is None or route.destination_iata == promo.destination_iata
        if origin_ok and dest_ok:
            return True

    return False


def filter_for_user(
    promos: list[PromotionData],
    prefs: UserPreferencesData,
) -> list[PromotionData]:
    """Retorna somente as promoções ativas que batem com as preferências do usuário."""
    now = datetime.now(UTC)
    active = [p for p in promos if p.ends_at is not None and p.ends_at > now]
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
    return {prefs.user_id: filter_for_user(promos, prefs) for prefs in all_prefs}


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
        flight_routes = [
            FlightRoute(
                origin_iata=r.get("origin_iata"),
                destination_iata=r.get("destination_iata"),
            )
            for r in (row.flight_routes or [])
        ]
        result.append(
            UserPreferencesData(
                user_id=str(row.user_id),
                email=row.email,
                name=row.name,
                phone=row.phone,
                unsubscribe_token=(str(row.unsubscribe_token) if row.unsubscribe_token else None),
                monitored_programs=row.monitored_programs or [],
                transfer_pairs=pairs,
                accumulation_programs=row.accumulation_programs or [],
                flight_routes=flight_routes,
                flight_programs=row.flight_programs or [],
            )
        )
    return result
