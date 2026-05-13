"""Testes de filtragem para promoções flight_award."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.pipeline.preference_filter import matches_preferences
from src.types import FlightRoute, PromotionData, UserPreferencesData

_FUTURE = datetime.now(UTC) + timedelta(days=7)


def _flight_promo(
    origin: str | None = "GRU",
    dest: str | None = "MIA",
    program: str = "azul",
) -> PromotionData:
    return PromotionData(
        fingerprint="fp-flight",
        source_program=program,
        source_type="rss",
        source_url="https://example.com",
        promo_type="flight_award",
        origin_iata=origin,
        destination_iata=dest,
        ends_at=_FUTURE,
    )


def _prefs(
    routes: list[tuple[str | None, str | None]] | None = None,
    programs: list[str] | None = None,
) -> UserPreferencesData:
    return UserPreferencesData(
        user_id="user-xyz",
        flight_routes=[FlightRoute(origin_iata=o, destination_iata=d) for o, d in (routes or [])],
        flight_programs=programs or [],
    )


def test_no_flight_prefs_no_match():
    assert matches_preferences(_flight_promo(), _prefs()) is False


def test_match_exact_route():
    assert matches_preferences(_flight_promo("GRU", "MIA"), _prefs(routes=[("GRU", "MIA")])) is True


def test_no_match_wrong_destination():
    assert (
        matches_preferences(_flight_promo("GRU", "CDG"), _prefs(routes=[("GRU", "MIA")])) is False
    )


def test_match_wildcard_destination():
    """origin=GRU, dest=None → qualquer destino saindo de GRU."""
    assert matches_preferences(_flight_promo("GRU", "CDG"), _prefs(routes=[("GRU", None)])) is True


def test_match_wildcard_origin():
    """origin=None, dest=MIA → qualquer origem chegando em MIA."""
    assert matches_preferences(_flight_promo("BSB", "MIA"), _prefs(routes=[(None, "MIA")])) is True


def test_no_match_wrong_origin():
    assert (
        matches_preferences(_flight_promo("GRU", "MIA"), _prefs(routes=[("BSB", "MIA")])) is False
    )


def test_match_by_program_only():
    # origin_program simula o programa detectado no artigo RSS
    promo = PromotionData(
        fingerprint="fp",
        source_program="unknown",  # RSS sempre retorna "unknown"
        source_type="rss",
        source_url="https://example.com",
        promo_type="flight_award",
        origin_program="azul",  # detectado no texto pelo extrator
        ends_at=_FUTURE,
    )
    assert matches_preferences(promo, _prefs(programs=["azul"])) is True


def test_no_match_wrong_program():
    promo = PromotionData(
        fingerprint="fp",
        source_program="unknown",
        source_type="rss",
        source_url="https://example.com",
        promo_type="flight_award",
        origin_program="smiles",
        ends_at=_FUTURE,
    )
    assert matches_preferences(promo, _prefs(programs=["azul"])) is False


def test_program_filter_blocks_wrong_program_even_with_matching_route():
    promo = _flight_promo("GRU", "MIA", program="smiles")
    prefs = _prefs(routes=[("GRU", "MIA")], programs=["azul"])
    assert matches_preferences(promo, prefs) is False


def test_multiple_routes_or_logic():
    promo = _flight_promo("GRU", "LHR")
    prefs = _prefs(routes=[("GRU", "MIA"), ("GRU", "LHR")])
    assert matches_preferences(promo, prefs) is True


def test_no_route_on_promo_matches_wildcard_pref():
    """Promo sem rota identificada: wildcard route deve dar match."""
    promo = _flight_promo(origin=None, dest=None)
    prefs = _prefs(routes=[(None, None)], programs=["azul"])
    assert matches_preferences(promo, prefs) is True
