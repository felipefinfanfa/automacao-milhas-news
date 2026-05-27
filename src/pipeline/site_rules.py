"""Regras de classificação por site para o extractor de promoções.

Prioridade de aplicação (alta → baixa):
  1. confirm_flight_award   → classifica como flight_award
  2. confirm_transfer_bonus → classifica como transfer_bonus
  3. confirm_accumulation   → classifica como other (acúmulo)
  4. reject_transfer_bonus  → impede classificação genérica como transfer_bonus
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SiteRule:
    confirm_flight_award: list[re.Pattern[str]] = field(default_factory=list)
    confirm_transfer_bonus: list[re.Pattern[str]] = field(default_factory=list)
    confirm_accumulation: list[re.Pattern[str]] = field(default_factory=list)
    reject_transfer_bonus: list[re.Pattern[str]] = field(default_factory=list)


def _p(*patterns: str) -> list[re.Pattern[str]]:
    return [re.compile(p, re.I) for p in patterns]


def _p_cs(*patterns: str) -> list[re.Pattern[str]]:
    return [re.compile(p) for p in patterns]


SITE_RULES: dict[str, SiteRule] = {
    "pontos_pra_voar": SiteRule(
        confirm_flight_award=[
            *_p(
                r"alerta\s+de\s+passagens\s+ppv",
                r"\d+\s*milhas\s*\+\s*taxas",
            ),
            *_p_cs(r"\b[A-Z]{3}\b.{0,10}\b[A-Z]{3}\b"),
        ],
        confirm_transfer_bonus=_p(
            r"b[oô]nus.*transfer[eê]ncia\s+de\s+\w+\s+para\s+\w+",
        ),
        confirm_accumulation=_p(
            r"\d+\s+pontos\s+por\s+real",
            r"\d+\s+pontos\s+por\s+d[oó]lar",
        ),
        reject_transfer_bonus=_p(
            r"status\s+gold",
            r"b[oô]nus\s+em\s+pontos\s+reward",
            r"pontos\s+reward",
        ),
    ),
    "melhores_cartoes": SiteRule(
        confirm_flight_award=_p(
            r"\d+[\.,]?\d*\s+milhas\s+o\s+trecho",
            r"a\s+partir\s+de\s+\d+\s+milhas",
            r"promo[çc][aã]o\s+de\s+final\s+de\s+semana",
        ),
        confirm_transfer_bonus=_p(
            r"b[oô]nus\s+na\s+transfer[eê]ncia",
            r"transfer[eê]ncia\s+de\s+\w+\s+para\s+\w+",
        ),
        reject_transfer_bonus=_p(
            r"compra\s+(direta\s+)?de\s+milhas",
            r"comprar\s+milhas",
            r"cashback",
        ),
    ),
    "mestre_das_milhas": SiteRule(
        confirm_flight_award=_p(
            r"\d+\s+milhas\s+o\s+trecho",
            r"\d+\s+milhas\s+por\s+trecho",
        ),
        confirm_transfer_bonus=_p(
            r"b[oô]nus.*transfer[eê]ncia",
        ),
        confirm_accumulation=_p(
            r"\d+\s+pontos\s+por\s+real",
            r"\d+\s+pontos\s+por\s+d[oó]lar",
        ),
        reject_transfer_bonus=_p(
            r"compra\s+de\s+milhas",
            r"\ban[aá]lise\b",
            r"\bparceria\b",
        ),
    ),
    "melhores_destinos": SiteRule(
        confirm_flight_award=_p(
            r"\d+\s+milhas\s+o\s+trecho",
            r"milhas\s+\+\s+taxas",
            r"a\s+partir\s+de\s+\d+\s+milhas",
        ),
        confirm_transfer_bonus=_p(
            r"b[oô]nus.*transfer[eê]ncia\s+de\s+\w+\s+para\s+\w+",
        ),
    ),
    "passageiro_de_primeira": SiteRule(
        reject_transfer_bonus=_p(
            r"compra\s+de\s+milhas",
            r"\bstatus\b",
            r"\bhotel\b",
        ),
    ),
}
