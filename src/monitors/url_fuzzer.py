"""Tier 3 — URL pattern fuzzing por histórico.

Gera variações de URLs de promoção com base em padrões históricos
(ano, mês, incrementos de campanha) e verifica quais retornam HTTP 200.
"""
import logging
import re
from datetime import datetime, timezone

import httpx

from src.config.settings import PROGRAM_URLS, settings
from src.types import RawSignal

logger = logging.getLogger(__name__)

_URL_PATTERN_RE = re.compile(
    r"(?P<base>https?://[^/]+/[^?#]*/)"
    r"(?P<slug>[a-z0-9-]+)"
    r"(?P<suffix>/[^?#]*)?"
)

_MONTH_NAMES_PT = [
    "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _generate_candidates(base_url: str) -> list[str]:
    now = datetime.now(timezone.utc)
    candidates: list[str] = []

    from urllib.parse import urlparse
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"

    year = now.year
    month_idx = now.month - 1

    for mo in range(max(0, month_idx - 1), min(12, month_idx + 3)):
        month_name = _MONTH_NAMES_PT[mo]
        for suffix in ["transferencia-bonificada", "bonus-transferencia", "campanha-transferencia"]:
            candidates.append(f"{origin}/promocoes/{suffix}-{month_name}-{year}")
            candidates.append(f"{origin}/promocoes/{year}/{month_name}/{suffix}")
            candidates.append(f"{origin}/{suffix}-{month_name}-{year}")

    return candidates


def _check_url(url: str) -> bool:
    try:
        from src.integrations.user_agents import get_current_ua
        with httpx.Client(
            headers={"User-Agent": get_current_ua()},
            follow_redirects=True,
            timeout=10,
        ) as client:
            resp = client.head(url)
            return resp.status_code == 200
    except Exception:
        return False


def scan_url_fuzzer(urls: dict[str, str] | None = None) -> list[RawSignal]:
    """Gera e testa variações de URLs de promoção."""
    if urls is None:
        urls = PROGRAM_URLS

    signals: list[RawSignal] = []

    for program, base_url in urls.items():
        candidates = _generate_candidates(base_url)
        found = [u for u in candidates if _check_url(u)]

        for url in found:
            logger.info("url_fuzzer: nova URL encontrada para %s — %s", program, url)
            signals.append(
                RawSignal(
                    source_url=url,
                    source_program=program,
                    source_type="url_fuzzer",
                    fetched_at=datetime.now(timezone.utc),
                    extra={"fuzzed": True},
                )
            )

    return signals
