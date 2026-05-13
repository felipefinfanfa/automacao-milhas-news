"""Extração estruturada de promoções a partir de RawSignals.

Seletores CSS e regex por programa ficam em PROGRAM_RULES.
Atualizar PROGRAM_RULES (e apenas aqui) quando um programa mudar layout.
"""

from __future__ import annotations

import calendar
import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from bs4 import BeautifulSoup

from src.config.airports import CITY_TO_IATA
from src.types import PromotionData, RawSignal

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
_END_DATE_CONTEXT_RE = re.compile(r"v[aá]lid[ao]|at[eé]|termina|encerra|expira|prazo|até", re.I)

_PROMO_KEYWORD_RE = re.compile(r"promo|b[oô]nus|transfer|campanha|oferta|milhas|pontos", re.I)

# Natural language date patterns (Portuguese)
_NL_TODAY_RE = re.compile(
    r"hoje\s+[eé]\s+o\s+[úu]ltimo\s+dia"
    r"|[úu]ltimo\s+dia\s+hoje"
    r"|v[áa]lido\s+at[eé]\s+hoje"
    r"|termina\s+hoje"
    r"|encerra\s+hoje"
    r"|expira\s+hoje"
    r"|s[oó]\s+hoje"
    r"|[úu]ltima\s+chance\s+hoje",
    re.I,
)
_NL_TOMORROW_RE = re.compile(
    r"v[áa]lido\s+at[eé]\s+amanh[ãa]"
    r"|termina\s+amanh[ãa]"
    r"|encerra\s+amanh[ãa]"
    r"|s[oó]\s+at[eé]\s+amanh[ãa]"
    r"|[úu]ltimo\s+dia\s+amanh[ãa]",
    re.I,
)
_NL_MONTH_END_RE = re.compile(
    r"at[eé]\s+o\s+fi(?:m|nal)\s+do\s+m[eê]s" r"|fi(?:m|nal)\s+do\s+m[eê]s",
    re.I,
)
_NL_WEEKDAY_RE = re.compile(
    r"at[eé]\s+(segunda|ter[cç]a|quarta|quinta|sexta|s[aá]bado|domingo)(?:\s*-?\s*feira)?",
    re.I,
)
_NL_WRITTEN_DATE_RE = re.compile(
    r"(\d{1,2})\s+de\s+"
    r"(janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto"
    r"|setembro|outubro|novembro|dezembro)"
    r"(?:\s+de\s+(\d{4}))?",
    re.I,
)

_WEEKDAY_MAP: dict[str, int] = {
    "segunda": 0,
    "terca": 1,
    "terça": 1,
    "quarta": 2,
    "quinta": 3,
    "sexta": 4,
    "sabado": 5,
    "sábado": 5,
    "domingo": 6,
}
_MONTH_MAP: dict[str, int] = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "março": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

PROGRAM_RULES: dict[str, dict[str, Any]] = {
    "smiles": {
        "promo_selectors": [
            ".promo-card",
            ".transferencia-card",
            "[class*='promoção']",
            ".campanha",
            "article.promo",
        ],
        "title_selectors": ["h1", "h2", ".card-title", ".promo-title"],
        "confidence_boost": 0.1,
    },
    "azul": {
        "promo_selectors": [
            ".card-promocao",
            ".transferencia",
            "[class*='bonus']",
            ".offer-card",
            "article",
        ],
        "title_selectors": ["h1", "h2", "h3", ".titulo"],
        "confidence_boost": 0.0,
    },
    "latam": {
        "promo_selectors": [
            ".promo-item",
            ".transfer-bonus",
            "[class*='campanha']",
            ".card",
            ".offer",
        ],
        "title_selectors": ["h1", "h2", "h3"],
        "confidence_boost": 0.0,
    },
    "livelo": {
        "promo_selectors": [
            ".card-oferta",
            ".transferencia-pontos",
            "[class*='promo']",
            ".promo",
            "article",
        ],
        "title_selectors": ["h1", "h2", ".card-title"],
        "confidence_boost": 0.05,
    },
    "esfera": {
        "promo_selectors": [
            ".promo-esfera",
            ".transferencia",
            "[class*='bonus']",
            ".card",
            "article",
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


def _parse_date_match(m: re.Match) -> datetime | None:
    d, mo, y = m.group(1), m.group(2), m.group(3)
    year = int(f"20{y}") if len(y) == 2 else int(y)
    try:
        return datetime(year, int(mo), int(d), tzinfo=UTC)
    except ValueError:
        return None


def _extract_natural_end_date(text: str, reference_date: datetime | None = None) -> datetime | None:
    """Infere ends_at de expressões em português como 'hoje é o último dia'.

    reference_date: data de publicação do artigo. "Hoje" é relativo a essa data,
    não à data atual do sistema. Para artigos RSS, é o published_parsed da entrada.
    """
    today = (reference_date or datetime.now(UTC)).date()

    def eod(d) -> datetime:
        return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=UTC)

    if _NL_TODAY_RE.search(text):
        return eod(today)

    if _NL_TOMORROW_RE.search(text):
        return eod(today + timedelta(days=1))

    if _NL_MONTH_END_RE.search(text):
        last_day = calendar.monthrange(today.year, today.month)[1]
        return eod(today.replace(day=last_day))

    m = _NL_WEEKDAY_RE.search(text)
    if m:
        target_wd = _WEEKDAY_MAP.get(m.group(1).lower())
        if target_wd is not None:
            days_ahead = (target_wd - today.weekday()) % 7 or 7
            return eod(today + timedelta(days=days_ahead))

    m = _NL_WRITTEN_DATE_RE.search(text)
    if m:
        day = int(m.group(1))
        month = _MONTH_MAP.get(m.group(2).lower())
        year = int(m.group(3)) if m.group(3) else today.year
        if month:
            try:
                d = datetime(year, month, day, 23, 59, 59, tzinfo=UTC)
                # No year given and date already passed → assume next year
                if not m.group(3) and d.date() < today:
                    d = d.replace(year=year + 1)
                return d
            except ValueError:
                pass

    return None


def _extract_date_range(
    text: str, reference_date: datetime | None = None
) -> tuple[datetime | None, datetime | None]:
    matches = list(_DATE_PATTERN.finditer(text))

    starts_at: datetime | None = None
    ends_at: datetime | None = None

    if len(matches) == 1:
        idx = matches[0].start()
        before = text[max(0, idx - 50) : idx]
        dt = _parse_date_match(matches[0])
        if _END_DATE_CONTEXT_RE.search(before):
            ends_at = dt
        else:
            starts_at = dt
    elif len(matches) >= 2:
        starts_at = _parse_date_match(matches[0])
        ends_at = _parse_date_match(matches[1])

    if ends_at is None:
        ends_at = _extract_natural_end_date(text, reference_date)

    return starts_at, ends_at


_TRANSFER_DIRECTION_RE = re.compile(
    r"(?P<origin>smiles|livelo|latam\s*pass|azul\s*fidelidade|azul|latam|esfera|iupp)"
    r"\s+(?:para|p/|->|→)\s+"
    r"(?P<dest>smiles|livelo|latam\s*pass|azul\s*fidelidade|azul|latam|esfera|iupp)",
    re.I,
)

_FLIGHT_AWARD_RE = re.compile(
    r"voos?\s+para\b"
    r"|voos?\s+saindo\b"
    r"|passagem\s+pr[eê]mio"
    r"|emiss[ãa]o\s+com"
    r"|emitir\s+com"
    r"|[\d\.,]+\s*(mil\s+)?(milhas|pontos)\s+(o\s+trecho|por\s+trecho)"
    r"|trechos?\s+a\s+partir\s+de\s+[\d\.,]+\s*(mil\s+)?(milhas|pontos)"
    r"|[\d\.,]+\s+mil\s+milhas\b"
    r"|[\d\.,]+\s+mil\s+pontos\b"
    r"|compartilhando\s+emiss[õo]es",
    re.I,
)

_MILES_COUNT_RE = re.compile(
    r"([\d\.,]+)\s*(mil\s+)?(milhas|pontos)\b",
    re.I,
)

_ROUTE_FROM_RE = re.compile(
    r"(?:de|saindo\s+de|partindo\s+de)\s+"
    r"([a-zà-ü\s]{3,30}?)"
    r"(?=\s+para\b|\s+com\b|\s+por\b|,|\.|$)",
    re.I,
)

_ROUTE_TO_RE = re.compile(
    r"(?:para|at[eé]|com\s+destino\s+a)\s+"
    r"(?:o\s+|a\s+|os\s+|as\s+)?"  # skip articles: "para o Caribe" → skip "o"
    r"([a-zà-ü\s]{3,30}?)"
    r"(?=\s+(?:com|por|a\s+partir|em|via)\b|,|\.|$|\s*\Z)",
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


def _extract_miles_count(text: str) -> int | None:
    """Extrai a maior contagem de milhas/pontos do texto. Ignora valores < 1000."""
    values: list[int] = []
    for m in _MILES_COUNT_RE.finditer(text):
        raw = m.group(1).replace(".", "").replace(",", "")
        is_mil = bool(m.group(2))
        try:
            val = int(raw)
            if is_mil:
                val *= 1000
            if val >= 1000:
                values.append(val)
        except ValueError:
            continue
    return max(values) if values else None


def _extract_route(text: str) -> tuple[str | None, str | None]:
    """Extrai (origin_iata, destination_iata) do texto via regex + CITY_TO_IATA."""

    def _lookup(city_raw: str) -> str | None:
        city = city_raw.strip().lower()
        if city in CITY_TO_IATA:
            return CITY_TO_IATA[city]
        for key, iata in CITY_TO_IATA.items():
            if city.startswith(key):
                return iata
        return None

    origin_iata: str | None = None
    destination_iata: str | None = None

    m_from = _ROUTE_FROM_RE.search(text)
    if m_from:
        origin_iata = _lookup(m_from.group(1))

    m_to = _ROUTE_TO_RE.search(text)
    if m_to:
        destination_iata = _lookup(m_to.group(1))

    return origin_iata, destination_iata


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

    full_text = f"{title or ''} {text}"
    # Use article publication date as reference for relative expressions ("hoje", "amanhã").
    # For RSS feeds, signal.fetched_at is set to published_parsed — not the scrape time.
    starts_at, ends_at = _extract_date_range(full_text, signal.fetched_at)
    if ends_at is None:
        return None

    # Discard promotions already expired relative to now, even if the article's
    # "today" was in the past (e.g. old RSS entry saying "hoje é o último dia").
    if ends_at < datetime.now(UTC):
        return None

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

    # transfer_bonus takes priority (needs explicit %).
    # flight_award second: no % bonus but flight patterns detected.
    if bonus_pct:
        promo_type = "transfer_bonus"
    elif _FLIGHT_AWARD_RE.search(full_text):
        promo_type = "flight_award"
    else:
        promo_type = "other"

    # Extract flight-specific fields
    origin_iata: str | None = None
    destination_iata: str | None = None
    miles_count: int | None = None
    if promo_type == "flight_award":
        miles_count = _extract_miles_count(full_text)
        origin_iata, destination_iata = _extract_route(full_text)

    # ends_at is always set at this point (gate above).
    fp_date = ends_at.date().isoformat()

    if promo_type == "flight_award":
        if origin_iata or destination_iata:
            fp = _fingerprint([origin_iata or "", destination_iata or "", "flight_award", fp_date])
        else:
            # No route resolved — use URL to prevent same-day collision across articles
            fp = _fingerprint([signal.source_url, "flight_award", fp_date])
    else:
        fp = _fingerprint(
            [
                origin,
                dest or "",
                str(int(bonus_pct)) if bonus_pct else "",
                promo_type,
                fp_date,
            ]
        )

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
        origin_iata=origin_iata,
        destination_iata=destination_iata,
        miles_count=miles_count,
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


def _extract_from_text(
    signal: RawSignal, source_program: str, confidence: float
) -> list[PromotionData]:
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
        "article",
        ".promo",
        ".campanha",
        ".card",
        "[class*='promo']",
        "[class*='bonus']",
    ]
    title_selectors = rules.get("title_selectors", ["h1", "h2", "h3", ".title"])

    blocks = soup.select(", ".join(selectors))

    if not blocks:
        body_text = soup.get_text(separator=" ", strip=True)
        promo = _make_promotion(
            signal=signal,
            text=body_text,
            title=soup.title.string.strip() if soup.title and soup.title.string else signal.title,
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
