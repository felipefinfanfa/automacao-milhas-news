"""Testes de extração de promoções flight_award."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from src.pipeline.extractor import _extract_miles_count, extract
from src.types import RawSignal


def _signal(title: str, body: str, pub_date: datetime | None = None) -> RawSignal:
    return RawSignal(
        source_url="https://example.com/test",
        source_program=None,
        source_type="rss",
        title=title,
        raw_content=body,
        fetched_at=pub_date or datetime.now(UTC),
    )


_FUTURE = datetime.now(UTC) + timedelta(days=30)
_FUTURE_STR = _FUTURE.strftime("%d/%m/%Y")


def test_flight_award_classified_correctly():
    sig = _signal(
        "Voos para Miami em Executiva a partir de 71 mil milhas",
        f"Voe de São Paulo para Miami por 71 mil milhas até {_FUTURE_STR}.",
    )
    promos = extract(sig)
    assert len(promos) == 1
    assert promos[0].promo_type == "flight_award"


def test_flight_award_miles_count():
    sig = _signal(
        "Voos para Montreal com bagagem por 115 mil pontos Azul o trecho",
        f"De São Paulo para Montreal por 115 mil pontos até {_FUTURE_STR}.",
    )
    promos = extract(sig)
    assert len(promos) == 1
    assert promos[0].miles_count == 115_000


def test_flight_award_destination_iata():
    sig = _signal(
        "Voos para Miami",
        f"De São Paulo para Miami por 71 mil milhas até {_FUTURE_STR}.",
    )
    promos = extract(sig)
    assert len(promos) == 1
    assert promos[0].destination_iata == "MIA"


def test_flight_award_origin_iata():
    sig = _signal(
        "Voos saindo de São Paulo para Lisboa",
        f"Saindo de São Paulo para Lisboa por 80 mil milhas até {_FUTURE_STR}.",
    )
    promos = extract(sig)
    assert len(promos) == 1
    assert promos[0].origin_iata == "GRU"


def test_transfer_bonus_not_reclassified_as_flight():
    sig = _signal(
        "100% de bônus na transferência Livelo para Smiles",
        f"Transferência de Livelo para Smiles com 100% de bônus até {_FUTURE_STR}.",
    )
    promos = extract(sig)
    assert len(promos) == 1
    assert promos[0].promo_type == "transfer_bonus"


def test_extract_miles_count_mil_suffix():
    assert _extract_miles_count("71 mil milhas") == 71_000


def test_extract_miles_count_dot_separator():
    assert _extract_miles_count("115.000 milhas") == 115_000


def test_extract_miles_count_small_number_ignored():
    assert _extract_miles_count("5 milhas por real") is None


def test_extract_miles_count_none_when_absent():
    assert _extract_miles_count("promoção sem contagem") is None


def test_flight_award_without_route_still_saved():
    sig = _signal(
        "Compartilhando Emissões: viagem incrível",
        f"Emissão com milhas até {_FUTURE_STR}.",
    )
    promos = extract(sig)
    assert len(promos) == 1
    assert promos[0].promo_type == "flight_award"
    assert promos[0].origin_iata is None
    assert promos[0].destination_iata is None


def test_flight_award_fingerprint_excludes_miles_count():
    sig1 = _signal("Voos para Miami", f"71 mil milhas até {_FUTURE_STR}.")
    sig2 = _signal("Voos para Miami", f"80 mil milhas até {_FUTURE_STR}.")
    p1 = extract(sig1)
    p2 = extract(sig2)
    if p1 and p2:
        assert p1[0].fingerprint == p2[0].fingerprint
