"""Testes de filtragem de promoções por preferências do usuário."""

from __future__ import annotations

from src.pipeline.preference_filter import filter_for_user, matches_preferences
from src.types import PromotionData, TransferPair, UserPreferencesData


def _make_transfer_promo(origin: str, dest: str, bonus: float = 100.0) -> PromotionData:
    return PromotionData(
        fingerprint=f"fp-{origin}-{dest}",
        source_program=origin,
        source_type="direct_scraper",
        source_url="https://example.com",
        promo_type="transfer_bonus",
        origin_program=origin,
        destination_program=dest,
        bonus_percent=bonus,
    )


def _make_accum_promo(program: str) -> PromotionData:
    return PromotionData(
        fingerprint=f"fp-accum-{program}",
        source_program=program,
        source_type="direct_scraper",
        source_url="https://example.com",
        promo_type="other",
        origin_program=program,
    )


def _make_prefs(transfer_pairs=None, accum_programs=None) -> UserPreferencesData:
    return UserPreferencesData(
        user_id="user-abc",
        monitored_programs=["smiles", "livelo"],
        transfer_pairs=[TransferPair(source=s, dest=d) for s, d in (transfer_pairs or [])],
        accumulation_programs=accum_programs or [],
    )


def test_transfer_pair_is_non_commutative():
    """Esfera→Smiles ≠ Smiles→Esfera."""
    promo_esfera_to_smiles = _make_transfer_promo("esfera", "smiles")
    promo_smiles_to_esfera = _make_transfer_promo("smiles", "esfera")

    prefs = _make_prefs(transfer_pairs=[("esfera", "smiles")])

    assert matches_preferences(promo_esfera_to_smiles, prefs) is True
    assert matches_preferences(promo_smiles_to_esfera, prefs) is False


def test_exact_transfer_pair_match():
    promo = _make_transfer_promo("livelo", "smiles")
    prefs = _make_prefs(transfer_pairs=[("livelo", "smiles")])
    assert matches_preferences(promo, prefs) is True


def test_no_match_wrong_dest():
    promo = _make_transfer_promo("livelo", "latam")
    prefs = _make_prefs(transfer_pairs=[("livelo", "smiles")])
    assert matches_preferences(promo, prefs) is False


def test_no_match_empty_pairs():
    promo = _make_transfer_promo("livelo", "smiles")
    prefs = _make_prefs(transfer_pairs=[])
    assert matches_preferences(promo, prefs) is False


def test_accumulation_match():
    promo = _make_accum_promo("livelo")
    prefs = _make_prefs(accum_programs=["livelo", "esfera"])
    assert matches_preferences(promo, prefs) is True


def test_accumulation_no_match():
    promo = _make_accum_promo("iupp")
    prefs = _make_prefs(accum_programs=["livelo", "esfera"])
    assert matches_preferences(promo, prefs) is False


def test_filter_for_user_returns_only_matching():
    promos = [
        _make_transfer_promo("livelo", "smiles"),
        _make_transfer_promo("esfera", "smiles"),
        _make_transfer_promo("livelo", "latam"),
    ]
    prefs = _make_prefs(transfer_pairs=[("livelo", "smiles"), ("esfera", "smiles")])
    result = filter_for_user(promos, prefs)
    assert len(result) == 2
    dest_set = {p.destination_program for p in result}
    assert dest_set == {"smiles"}


def test_filter_for_user_empty_when_no_prefs():
    promos = [_make_transfer_promo("livelo", "smiles")]
    prefs = _make_prefs()
    assert filter_for_user(promos, prefs) == []


def test_case_insensitive_matching():
    promo = _make_transfer_promo("Livelo", "Smiles")
    prefs = _make_prefs(transfer_pairs=[("livelo", "smiles")])
    assert matches_preferences(promo, prefs) is True
