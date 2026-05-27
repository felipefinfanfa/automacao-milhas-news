"""Testes para regras de extração por site e correções no extractor."""
from __future__ import annotations

from datetime import UTC, datetime

from src.pipeline.extractor import _find_programs, extract
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


# ---------------------------------------------------------------------------
# Task 3 — classificação por site via extract()
# ---------------------------------------------------------------------------


class TestClassificacaoPorSite:
    def test_regression_all_accor_is_other(self):
        """Bug original: artigo Esfera→ALL Accor era classificado como transfer_bonus esfera→smiles."""
        sig = _signal(
            "Transfira pontos Esfera e garanta status Gold ALL Accor",
            (
                "Transfira 52.500 pontos Esfera para ganhar status Gold temporário no ALL Accor. "
                "48% de bônus em pontos Reward durante estadias no hotel. "
                + _DATE_OK
            ),
            "pontos_pra_voar",
        )
        results = extract(sig)
        assert len(results) == 1
        p = results[0]
        assert p.promo_type == "other"
        assert p.destination_program is None

    def test_alerta_ppv_is_flight_award(self):
        sig = _signal(
            "Alerta de passagens PPV! 3.040 milhas + taxas LATAM Pass",
            (
                "Alerta de passagens PPV. Confira trechos: VIX para GIG 3.040 milhas + taxas. "
                "GIG para VIX 3.080 milhas + taxas. "
                + _DATE_OK
            ),
            "pontos_pra_voar",
        )
        results = extract(sig)
        assert len(results) == 1
        assert results[0].promo_type == "flight_award"

    def test_accumulation_esfera_is_other(self):
        sig = _signal(
            "Esfera oferece até 18 pontos por real em compras online",
            "Esfera oferece 18 pontos por real gasto em compras via hotlinks parceiros. " + _DATE_OK,
            "pontos_pra_voar",
        )
        results = extract(sig)
        assert len(results) == 1
        assert results[0].promo_type == "other"

    def test_compra_de_milhas_smiles_is_other(self):
        """'365% de bônus na compra de milhas' não é transfer_bonus."""
        sig = _signal(
            "Smiles oferece até 365% de bônus na compra de milhas",
            (
                "365% de bônus na compra direta de milhas Smiles. "
                "1.000 milhas Smiles a partir de R$ 17,20. Limite de 300.000 milhas por CPF. "
                + _DATE_OK
            ),
            "melhores_cartoes",
        )
        results = extract(sig)
        assert len(results) == 1
        assert results[0].promo_type == "other"

    def test_flight_award_melhores_cartoes(self):
        sig = _signal(
            "Voos promocionais da Latam a partir de 3.262 milhas o trecho",
            (
                "LATAM Pass oferece passagens a partir de 3.262 milhas o trecho. "
                "Promoção de final de semana válida para diversas rotas. "
                + _DATE_OK
            ),
            "melhores_cartoes",
        )
        results = extract(sig)
        assert len(results) == 1
        assert results[0].promo_type == "flight_award"

    def test_real_transfer_bonus_pontos_pra_voar(self):
        sig = _signal(
            "80% de bônus na transferência de Livelo para Smiles",
            (
                "Aproveite 80% de bônus na transferência de Livelo para Smiles. "
                "Transferência mínima de 1.000 pontos. "
                + _DATE_OK
            ),
            "pontos_pra_voar",
        )
        results = extract(sig)
        assert len(results) == 1
        p = results[0]
        assert p.promo_type == "transfer_bonus"
        assert p.origin_program == "livelo"
        assert p.destination_program == "smiles"

    def test_accumulation_mestre_das_milhas_is_other(self):
        sig = _signal(
            "Livelo lança campanha de 10 pontos por real",
            "Livelo oferece 10 pontos por real gasto em parceiros de viagem. " + _DATE_OK,
            "mestre_das_milhas",
        )
        results = extract(sig)
        assert len(results) == 1
        assert results[0].promo_type == "other"

    def test_flight_award_mestre_das_milhas(self):
        sig = _signal(
            "Passagens LATAM Pass a partir de 5.000 milhas o trecho",
            "Emita passagens LATAM Pass a partir de 5.000 milhas o trecho para destinos nacionais. " + _DATE_OK,
            "mestre_das_milhas",
        )
        results = extract(sig)
        assert len(results) == 1
        assert results[0].promo_type == "flight_award"
