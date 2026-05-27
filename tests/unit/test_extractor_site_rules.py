"""Testes para regras de extração por site e correções no extractor."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.pipeline.extractor import _find_programs
from src.types import RawSignal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATE_OK = "Válido até 28/05/2026."


def _signal(title: str, body: str, source_id: str) -> RawSignal:
    return RawSignal(
        source_url="https://example.com/test",
        source_type="rss",
        title=title,
        raw_content=body,
        fetched_at=datetime(2026, 5, 27, tzinfo=UTC),
        extra={"feed_source": source_id},
    )


# ---------------------------------------------------------------------------
# Task 1 — word boundary em _find_programs
# ---------------------------------------------------------------------------

class TestFindProgramsWordBoundary:
    def test_gol_does_not_match_inside_gold(self):
        result = _find_programs("status Gold ALL Accor Esfera")
        assert "smiles" not in result
        assert "esfera" in result

    def test_gol_matches_standalone(self):
        result = _find_programs("Transferência Gol Smiles LATAM")
        assert "smiles" in result

    def test_latam_inside_word_not_matched(self):
        # "multilatam" não deve virar latam
        result = _find_programs("programa multilatam especial")
        assert "latam" not in result

    def test_esfera_matched_normally(self):
        result = _find_programs("Pontos Esfera para Livelo")
        assert "esfera" in result
        assert "livelo" in result
