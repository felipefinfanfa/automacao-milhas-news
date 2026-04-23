"""Tier 1 — Google News RSS por keyword."""
import logging
import urllib.parse
from datetime import datetime, timezone

import feedparser

from src.config.settings import GOOGLE_NEWS_KEYWORDS
from src.integrations.http_client import fetch
from src.types import RawSignal

logger = logging.getLogger(__name__)

_GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-419"


def _build_url(keyword: str) -> str:
    return _GOOGLE_NEWS_RSS.format(query=urllib.parse.quote_plus(keyword))


def scan_google_news(keywords: list[str] | None = None) -> list[RawSignal]:
    """Lê Google News RSS para cada keyword e retorna sinais brutos."""
    if keywords is None:
        keywords = GOOGLE_NEWS_KEYWORDS

    signals: list[RawSignal] = []

    for keyword in keywords:
        url = _build_url(keyword)
        try:
            content = fetch(url)
            parsed = feedparser.parse(content)
            for entry in parsed.entries:
                pub_date: datetime | None = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                signals.append(
                    RawSignal(
                        source_url=getattr(entry, "link", url),
                        source_program=None,
                        source_type="google_news",
                        title=getattr(entry, "title", None),
                        raw_content=getattr(entry, "summary", None),
                        fetched_at=pub_date or datetime.now(timezone.utc),
                        extra={"keyword": keyword},
                    )
                )
            logger.info("Google News '%s': %d resultados", keyword, len(parsed.entries))
        except Exception as exc:
            logger.warning("Falha no Google News para '%s': %s", keyword, exc)

    return signals
