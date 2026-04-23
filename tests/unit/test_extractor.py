"""Testes do extractor por programa com fixture HTML/RSS real."""
from __future__ import annotations

from datetime import timezone

import pytest

from src.processor.extractor import (
    _extract_bonus_pct,
    _extract_date_range,
    _find_programs,
    extract,
)
from src.types import RawSignal


def test_extract_bonus_pct_direct():
    assert _extract_bonus_pct("100% de bônus") == 100.0


def test_extract_bonus_pct_inverted():
    assert _extract_bonus_pct("bônus de 80%") == 80.0


def test_extract_bonus_pct_transfer():
    assert _extract_bonus_pct("transferência com 60% de bônus") == 60.0


def test_extract_bonus_pct_none():
    assert _extract_bonus_pct("novos destinos disponíveis") is None


def test_extract_date_range_two_dates():
    text = "promoção de 01/05/2026 a 31/05/2026"
    start, end = _extract_date_range(text)
    assert start is not None
    assert start.day == 1
    assert start.month == 5
    assert end is not None
    assert end.day == 31


def test_extract_date_range_end_only():
    text = "válido até 31/05/2026"
    start, end = _extract_date_range(text)
    assert start is None
    assert end is not None
    assert end.day == 31


def test_extract_date_range_none():
    start, end = _extract_date_range("promoção sem data")
    assert start is None
    assert end is None


def test_find_programs_ordered():
    text = "Transfira de Livelo para Smiles"
    programs = _find_programs(text)
    assert "livelo" in programs
    assert "smiles" in programs
    assert programs.index("livelo") < programs.index("smiles")


def test_extract_from_html_smiles(smiles_html):
    signal = RawSignal(
        source_url="https://www.smiles.com.br/transferencia",
        source_program="smiles",
        source_type="direct_scraper",
        raw_content=smiles_html,
    )
    promos = extract(signal)
    assert len(promos) > 0
    assert any(p.bonus_percent == 100.0 for p in promos)
    assert any(p.origin_program == "livelo" for p in promos)
    assert any(p.destination_program == "smiles" for p in promos)


def test_extract_from_html_latam(latam_html):
    signal = RawSignal(
        source_url="https://www.latam.com/promo",
        source_program="latam",
        source_type="direct_scraper",
        raw_content=latam_html,
    )
    promos = extract(signal)
    assert len(promos) > 0
    assert any(p.bonus_percent == 80.0 for p in promos)


def test_extract_from_rss(rss_xml):
    import feedparser

    parsed = feedparser.parse(rss_xml)
    assert len(parsed.entries) > 0

    entry = parsed.entries[0]
    signal = RawSignal(
        source_url=entry.link,
        source_program=None,
        source_type="rss",
        title=entry.title,
        raw_content=entry.get("summary", entry.get("description", "")),
        extra={"feed_source": "melhores_destinos"},
    )
    promos = extract(signal)
    assert len(promos) > 0
    bonus_promos = [p for p in promos if p.bonus_percent is not None]
    assert len(bonus_promos) > 0


def test_extract_no_content():
    signal = RawSignal(
        source_url="https://example.com",
        source_type="rss",
        raw_content=None,
    )
    assert extract(signal) == []


def test_extract_no_promo_keywords():
    signal = RawSignal(
        source_url="https://example.com",
        source_type="rss",
        title="Previsão do tempo para São Paulo",
        raw_content="Temperatura amena esperada para o fim de semana.",
    )
    assert extract(signal) == []
