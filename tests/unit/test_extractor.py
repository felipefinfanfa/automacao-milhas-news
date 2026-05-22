"""Testes do extractor por programa com fixture HTML/RSS real."""

from __future__ import annotations

from datetime import UTC, datetime

from src.pipeline.extractor import (
    _extract_bonus_pct,
    _extract_date_range,
    _extract_natural_end_date,
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


def test_extract_date_range_prefers_explicit_end_context_over_position():
    """Quando há contexto 'válido até X', X é o end_date mesmo se houver datas antes."""
    text = "Artigo publicado em 22/05/2026. Promoção válida até 15/06/2026."
    start, end = _extract_date_range(text)
    assert end is not None
    assert end.day == 15 and end.month == 6
    # 22/05 é uma data candidata a start (sem contexto de fim) e anterior ao end
    assert start is not None
    assert start.day == 22


def test_extract_date_range_ignores_unrelated_past_dates():
    """Datas isoladas no texto (e.g. de artigos relacionados) não viram end_date."""
    text = "Em 13/08/2025 lançamos a promoção anterior. " "Agora a nova é válida até 30/06/2026."
    start, end = _extract_date_range(text)
    assert end is not None
    assert end.day == 30 and end.month == 6 and end.year == 2026


def test_find_programs_ordered():
    text = "Transfira de Livelo para Smiles"
    programs = _find_programs(text)
    assert "livelo" in programs
    assert "smiles" in programs
    assert programs.index("livelo") < programs.index("smiles")


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


# --- Natural language date extraction ---


def test_natural_end_date_hoje(monkeypatch):
    fixed = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("src.pipeline.extractor.datetime", _FakeDatetime(fixed))
    result = _extract_natural_end_date("hoje é o último dia da promoção")
    assert result is not None
    assert result.day == 27 and result.month == 4 and result.year == 2026


def test_natural_end_date_termina_hoje(monkeypatch):
    fixed = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("src.pipeline.extractor.datetime", _FakeDatetime(fixed))
    result = _extract_natural_end_date("transferência com bônus, termina hoje")
    assert result is not None
    assert result.day == 27


def test_natural_end_date_amanha(monkeypatch):
    fixed = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("src.pipeline.extractor.datetime", _FakeDatetime(fixed))
    result = _extract_natural_end_date("válido até amanhã, não perca")
    assert result is not None
    assert result.day == 28 and result.month == 4


def test_natural_end_date_fim_do_mes(monkeypatch):
    fixed = datetime(2026, 4, 10, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("src.pipeline.extractor.datetime", _FakeDatetime(fixed))
    result = _extract_natural_end_date("promoção válida até o fim do mês")
    assert result is not None
    assert result.day == 30 and result.month == 4


def test_natural_end_date_written_date_with_year(monkeypatch):
    fixed = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("src.pipeline.extractor.datetime", _FakeDatetime(fixed))
    result = _extract_natural_end_date("válido até 30 de abril de 2026")
    assert result is not None
    assert result.day == 30 and result.month == 4 and result.year == 2026


def test_natural_end_date_written_date_no_year(monkeypatch):
    fixed = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("src.pipeline.extractor.datetime", _FakeDatetime(fixed))
    result = _extract_natural_end_date("promoção até 30 de abril")
    assert result is not None
    assert result.day == 30 and result.month == 4 and result.year == 2026


def test_natural_end_date_written_date_past_advances_year(monkeypatch):
    fixed = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("src.pipeline.extractor.datetime", _FakeDatetime(fixed))
    result = _extract_natural_end_date("promoção até 30 de abril")
    assert result is not None
    assert result.year == 2027


def test_natural_end_date_none():
    result = _extract_natural_end_date("promoção sem qualquer indicação de data")
    assert result is None


def test_extract_discards_promo_without_end_date():
    signal = RawSignal(
        source_url="https://example.com/promo",
        source_type="rss",
        title="100% de bônus Livelo para Smiles",
        raw_content="Transferência bonificada imperdível, sem data definida.",
    )
    assert extract(signal) == []


def test_extract_accepts_natural_language_end_date(monkeypatch):
    fixed = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr("src.pipeline.extractor.datetime", _FakeDatetime(fixed))
    signal = RawSignal(
        source_url="https://example.com/promo",
        source_type="rss",
        title="100% de bônus Livelo para Smiles",
        raw_content="Hoje é o último dia desta transferência bonificada.",
        fetched_at=fixed,  # artigo publicado em 27/04 — "hoje" é 27/04
    )
    promos = extract(signal)
    assert len(promos) == 1
    assert promos[0].ends_at is not None
    assert promos[0].ends_at.day == 27


def test_extract_discards_expired_from_old_article():
    """Artigo antigo dizendo 'hoje é o último dia' deve ser descartado."""
    article_date = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
    signal = RawSignal(
        source_url="https://example.com/promo",
        source_type="rss",
        title="100% de bônus Livelo para Smiles",
        raw_content="Hoje é o último dia desta transferência bonificada.",
        fetched_at=article_date,  # publicado em março → ends_at = 15/03 → expirado
    )
    promos = extract(signal)
    assert promos == []


class _FakeDatetime:
    """Substitui datetime.now(UTC) nos testes sem quebrar o restante da API."""

    def __init__(self, fixed: datetime):
        self._fixed = fixed

    def now(self, tz=None) -> datetime:
        return self._fixed

    def __call__(self, *args, **kwargs) -> datetime:
        return datetime(*args, **kwargs)


def test_extract_no_promo_keywords():
    signal = RawSignal(
        source_url="https://example.com",
        source_type="rss",
        title="Previsão do tempo para São Paulo",
        raw_content="Temperatura amena esperada para o fim de semana.",
    )
    assert extract(signal) == []
