"""Extração estruturada de promoções a partir de RawSignals.

Seletores CSS e regex por programa ficam em PROGRAM_RULES.
Atualizar PROGRAM_RULES (e apenas aqui) quando um programa mudar layout.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

from src.types import PromotionData, RawSignal, SourceType

logger = logging.getLogger(__name__)

_KNOWN_PROGRAMS = {"smiles", "azul", "latam", "livelo", "esfera", "iupp"}

_PROGRAM_LABELS: dict[str, str] = {
    "smiles": "smiles",
    "gol": "smiles",
    "latam": "latam",
    "latam pass": "latam",
    "azul": "azul",
    "azul fidelidade": "azul",
    "livelo": "livelo",
    "esfera": "esfera",
    "iupp": "iupp",
    "multiplus": "latam",
}

BONUS_PATTERNS = [
    re.compile(r"(\d{2,3})%\s*de\s*b[oô]nus", re.I),
    re.compile(r"b[oô]nus\s*de\s*(\d{2,3})%", re.I),
    re.compile(r"transfer[eê]ncia.*?(\d{2,3})%", re.I),
    re.compile(r"(\d{2,3})\s*por\s*cento", re.I),
    re.compile(r"\+\s*(\d{2,3})\s*%", re.I),
]

_DATE_PATTERN = re.compile(r"(\d{2})[/\-](\d{2})[/\-](\d{2,4})")
_END_DATE_CONTEXT_RE = re.compile(
    r"v[aá]lid[ao]|at[eé]|termina|encerra|expira|prazo|até", re.I
)

_PROMO_KEYWORD_RE = re.compile(
    r"promo|b[oô]nus|transfer|campanha|oferta|milhas|pontos", re.I
)

PROGRAM_RULES: dict[str, dict[str, Any]] = {
    "smiles": {
        "promo_selectors": [
            ".promo-card", ".transferencia-card", "[class*='promoção']",
            ".campanha", "article.promo",
        ],
        "title_selectors": ["h1", "h2", ".card-title", ".promo-title"],
        "confidence_boost": 0.1,
    },
    "azul": {
        "promo_selectors": [
            ".card-promocao", ".transferencia", "[class*='bonus']",
            ".offer-card", "article",
        ],
        "title_selectors": ["h1", "h2", "h3", ".titulo"],
        "confidence_boost": 0.0,
    },
    "latam": {
        "promo_selectors": [
            ".promo-item", ".transfer-bonus", "[class*='campanha']",
            ".card", ".offer",
        ],
        "title_selectors": ["h1", "h2", "h3"],
        "confidence_boost": 0.0,
    },
    "livelo": {
        "promo_selectors": [
            ".card-oferta", ".transferencia-pontos", "[class*='promo']",
            ".promo", "article",
        ],
        "title_selectors": ["h1", "h2", ".card-title"],
        "confidence_boost": 0.05,
    },
    "esfera": {
        "promo_selectors": [
            ".promo-esfera", ".transferencia", "[class*='bonus']",
            ".card", "article",
        ],
        "title_selectors": ["h1", "h2", "h3"],
        "confidence_boost": 0.0,
    },
    "iupp": {
        "promo_selectors": ["article", ".promo", ".card", "[class*='bonus']"],
        "title_selectors": ["h1", "h2", "h3"],
        "confidence_boost": 0.0,
    },
}


def _fingerprint(fields: list[str]) -> str:
    normalized = [f.strip().lower() if f else "" for f in fields]
    return hashlib.sha256(json.dumps(normalized).encode()).hexdigest()


def _extract_bonus_pct(text: str) -> float | None:
    for pattern in BONUS_PATTERNS:
        m = pattern.search(text)
        if m:
            try:
                return float(m.group(1))
            except (ValueError, IndexError):
                continue
    return None


def _extract_date_range(text: str) -> tuple[datetime | None, datetime | None]:
    matches = list(_DATE_PATTERN.finditer(text))
    if not matches:
        return None, None

    def to_dt(m: re.Match) -> datetime | None:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        year = int(f"20{y}") if len(y) == 2 else int(y)
        try:
            return datetime(year, int(mo), int(d), tzinfo=timezone.utc)
        except ValueError:
            return None

    if len(matches) == 1:
        idx = matches[0].start()
        before = text[max(0, idx - 50): idx]
        is_end = bool(_END_DATE_CONTEXT_RE.search(before))
        dt = to_dt(matches[0])
        return (None, dt) if is_end else (dt, None)

    return to_dt(matches[0]), to_dt(matches[1])


_TRANSFER_DIRECTION_RE = re.compile(
    r"(?P<origin>smiles|livelo|latam\s*pass|azul\s*fidelidade|azul|latam|esfera|iupp)"
    r"\s+(?:para|p/|->|→)\s+"
    r"(?P<dest>smiles|livelo|latam\s*pass|azul\s*fidelidade|azul|latam|esfera|iupp)",
    re.I,
)


def _find_transfer_direction(text: str) -> tuple[str | None, str | None]:
    """Detecta direção de transferência por padrão 'X para Y'."""
    m = _TRANSFER_DIRECTION_RE.search(text)
    if not m:
        return None, None
    origin_raw = m.group("origin").lower().strip()
    dest_raw = m.group("dest").lower().strip()
    origin = _PROGRAM_LABELS.get(origin_raw)
    dest = _PROGRAM_LABELS.get(dest_raw)
    return origin, dest


def _find_programs(text: str) -> list[str]:
    lower = text.lower()
    hits: list[tuple[int, str]] = []
    for key, val in _PROGRAM_LABELS.items():
        pos = lower.find(key)
        if pos != -1:
            hits.append((pos, val))
    hits.sort(key=lambda x: x[0])
    seen: set[str] = set()
    result: list[str] = []
    for _, val in hits:
        if val not in seen:
            seen.add(val)
            result.append(val)
    return result


def _make_promotion(
    *,
    signal: RawSignal,
    text: str,
    title: str | None,
    source_program: str,
    confidence: float,
) -> PromotionData | None:
    bonus_pct = _extract_bonus_pct(text)
    if not _PROMO_KEYWORD_RE.search(f"{title or ''} {text}"):
        return None

    starts_at, ends_at = _extract_date_range(text)
    full_text = f"{title or ''} {text}"
    # Prioridade: padrão direcional "X para Y" → ordem no texto → source_program
    dir_origin, dir_dest = _find_transfer_direction(full_text)
    if dir_origin:
        origin, dest = dir_origin, dir_dest
    else:
        programs = _find_programs(full_text)
        if len(programs) >= 2:
            origin, dest = programs[0], programs[1]
        elif len(programs) == 1:
            origin, dest = programs[0], None
        else:
            origin, dest = source_program, None

    promo_type = "transfer_bonus" if bonus_pct else "other"
    fp_date = starts_at.date().isoformat() if starts_at else signal.source_url

    fp = _fingerprint([
        origin,
        dest or "",
        str(int(bonus_pct)) if bonus_pct else "",
        promo_type,
        fp_date,
    ])

    return PromotionData(
        fingerprint=fp,
        source_program=source_program,
        source_type=signal.source_type,
        source_url=signal.source_url,
        title=title,
        promo_type=promo_type,  # type: ignore[arg-type]
        origin_program=origin,
        destination_program=dest,
        bonus_percent=bonus_pct,
        starts_at=starts_at,
        ends_at=ends_at,
        confidence=min(1.0, confidence),
        raw_data={
            "source_url": signal.source_url,
            "source_type": signal.source_type,
            "extra": signal.extra,
        },
    )


def extract(signal: RawSignal) -> list[PromotionData]:
    """Extrai promoções estruturadas de um RawSignal."""
    if not signal.raw_content:
        return []

    source_program = signal.source_program or "unknown"
    rules = PROGRAM_RULES.get(source_program, {})
    base_confidence = 0.6 + rules.get("confidence_boost", 0.0)

    source_type = signal.source_type

    if source_type in ("rss", "google_news"):
        return _extract_from_text(signal, source_program, base_confidence)

    if source_type in ("direct_scraper", "hash_diff"):
        return _extract_from_html(signal, source_program, rules, base_confidence)

    return _extract_from_text(signal, source_program, base_confidence * 0.8)


def _extract_from_text(signal: RawSignal, source_program: str, confidence: float) -> list[PromotionData]:
    text = f"{signal.title or ''} {signal.raw_content or ''}"
    promo = _make_promotion(
        signal=signal,
        text=text,
        title=signal.title,
        source_program=source_program,
        confidence=confidence,
    )
    return [promo] if promo else []


def _extract_from_html(
    signal: RawSignal,
    source_program: str,
    rules: dict[str, Any],
    confidence: float,
) -> list[PromotionData]:
    soup = BeautifulSoup(signal.raw_content or "", "lxml")
    promotions: list[PromotionData] = []

    selectors = rules.get("promo_selectors", []) + [
        "article", ".promo", ".campanha", ".card", "[class*='promo']", "[class*='bonus']"
    ]
    title_selectors = rules.get("title_selectors", ["h1", "h2", "h3", ".title"])

    blocks = soup.select(", ".join(selectors))

    if not blocks:
        body_text = soup.get_text(separator=" ", strip=True)
        promo = _make_promotion(
            signal=signal,
            text=body_text,
            title=soup.title.string.strip() if soup.title else signal.title,
            source_program=source_program,
            confidence=confidence * 0.8,
        )
        if promo:
            promotions.append(promo)
        return promotions

    for block in blocks:
        text = block.get_text(separator=" ", strip=True)
        if len(text) < 20:
            continue
        title_el = block.select_one(", ".join(title_selectors))
        title = title_el.get_text(strip=True) if title_el else None

        promo = _make_promotion(
            signal=signal,
            text=f"{title or ''} {text}",
            title=title,
            source_program=source_program,
            confidence=confidence,
        )
        if promo:
            promotions.append(promo)

    return promotions
