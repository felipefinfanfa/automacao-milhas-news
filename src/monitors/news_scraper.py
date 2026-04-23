"""Tier 2 — Scraping direto de notícias de blogs sem RSS disponível.

Usado apenas como fallback quando o RSS de uma fonte não está disponível.
Para fontes com RSS, usar rss_monitor.py.
"""
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from src.integrations.http_client import fetch
from src.types import RawSignal

logger = logging.getLogger(__name__)

_PROMO_RE = re.compile(r"promo|bônus|bonus|transfer|campanha|oferta|milhas", re.I)

NEWS_SCRAPER_SOURCES: dict[str, str] = {}


def scan_news_page(source_id: str, url: str) -> list[RawSignal]:
    """Faz scraping de uma página de notícias e retorna artigos relevantes."""
    try:
        content = fetch(url)
        soup = BeautifulSoup(content, "lxml")
        signals: list[RawSignal] = []

        articles = soup.select("article, .post, .entry, [class*='post'], [class*='article']")
        for article in articles:
            title_el = article.select_one("h1, h2, h3, .entry-title, .post-title")
            link_el = article.select_one("a[href]")
            title = title_el.get_text(strip=True) if title_el else None
            article_url = link_el["href"] if link_el else url

            if title and _PROMO_RE.search(title):
                signals.append(
                    RawSignal(
                        source_url=str(article_url),
                        source_program=None,
                        source_type="news_scraper",
                        title=title,
                        raw_content=article.get_text(separator=" ", strip=True)[:3000],
                        fetched_at=datetime.now(timezone.utc),
                        extra={"news_source": source_id},
                    )
                )

        logger.info("news_scraper %s: %d artigos de promo encontrados", source_id, len(signals))
        return signals
    except Exception as exc:
        logger.warning("Falha ao fazer scraping de %s (%s): %s", source_id, url, exc)
        return []


def scan_all_news() -> list[RawSignal]:
    """Faz scraping de todas as fontes configuradas em NEWS_SCRAPER_SOURCES."""
    signals: list[RawSignal] = []
    for source_id, url in NEWS_SCRAPER_SOURCES.items():
        signals.extend(scan_news_page(source_id, url))
    return signals
