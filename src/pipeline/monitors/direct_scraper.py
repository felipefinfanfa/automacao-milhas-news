"""Tier 1 — Landing pages dos programas via cloudscraper + BeautifulSoup4."""

import logging
from datetime import UTC, datetime

from bs4 import BeautifulSoup

from src.config.settings import PROGRAM_URLS
from src.tools.http_client import fetch
from src.types import RawSignal

logger = logging.getLogger(__name__)

_PROMO_SELECTORS = [
    "article",
    ".promo",
    ".campanha",
    ".card",
    ".offer",
    "[class*='promo']",
    "[class*='bonus']",
    "[class*='campanha']",
    "[class*='transferencia']",
    "[class*='transferência']",
]


def scan_landing_page(program: str, url: str) -> list[RawSignal]:
    """Faz scraping da landing page de um programa e retorna sinais."""
    try:
        content = fetch(url)
        soup = BeautifulSoup(content, "lxml")

        signals: list[RawSignal] = []

        promo_blocks = soup.select(", ".join(_PROMO_SELECTORS))

        if promo_blocks:
            for block in promo_blocks:
                text = block.get_text(separator=" ", strip=True)
                if len(text) < 20:
                    continue
                title_el = block.select_one("h1, h2, h3, h4, .title, .titulo")
                title = title_el.get_text(strip=True) if title_el else None

                signals.append(
                    RawSignal(
                        source_url=url,
                        source_program=program,
                        source_type="direct_scraper",
                        title=title,
                        raw_content=text[:5000],
                        fetched_at=datetime.now(UTC),
                        extra={"block_selector": "promo_block"},
                    )
                )
        else:
            body_text = soup.get_text(separator=" ", strip=True)
            signals.append(
                RawSignal(
                    source_url=url,
                    source_program=program,
                    source_type="direct_scraper",
                    title=soup.title.string.strip() if soup.title and soup.title.string else None,
                    raw_content=body_text[:5000],
                    fetched_at=datetime.now(UTC),
                    extra={"block_selector": "full_body"},
                )
            )

        logger.info("direct_scraper %s: %d blocos extraídos", program, len(signals))
        return signals

    except Exception as exc:
        logger.warning("Falha ao fazer scraping de %s (%s): %s", program, url, exc)
        return []


def scan_all_programs(urls: dict[str, str] | None = None) -> list[RawSignal]:
    """Executa scan_landing_page para todos os programas configurados."""
    if urls is None:
        urls = PROGRAM_URLS

    signals: list[RawSignal] = []
    for program, url in urls.items():
        signals.extend(scan_landing_page(program, url))
    return signals
