"""Testes do mapeamento cidade → IATA."""

from src.config.airports import AIRPORTS_LIST, CITY_TO_IATA


def test_key_cities_mapped():
    assert CITY_TO_IATA["são paulo"] == "GRU"
    assert CITY_TO_IATA["miami"] == "MIA"
    assert CITY_TO_IATA["montreal"] == "YUL"
    assert CITY_TO_IATA["paris"] == "CDG"
    assert CITY_TO_IATA["joanesburgo"] == "JNB"


def test_airports_list_unique_iata():
    codes = [a["iata"] for a in AIRPORTS_LIST]
    assert len(codes) == len(set(codes)), "Códigos IATA duplicados em AIRPORTS_LIST"


def test_airports_list_has_required_fields():
    for entry in AIRPORTS_LIST:
        assert "iata" in entry
        assert "label" in entry
        assert len(entry["iata"]) == 3
