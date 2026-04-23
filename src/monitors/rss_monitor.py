"""Tier 1 — RSS dos blogs de notícias de milhas."""
import logging
from datetime import datetime, timezone

import feedparser

from src.config.settings import NEWS_RSS_FEEDS
from src.integrations.http_client import fetch
from src.types import RawSignal

logger = logging.getLogger(__name__)


def scan_rss(feeds: dict[str, str] | None = None) -> list[RawSignal]:
    """Lê os feeds RSS dos blogs de milhas e retorna sinais brutos.

    Domínios distintos são processados sequencialmente (sem paralelismo
    no mesmo domínio), respeitando delays do http_client.
    """
    if feeds is None:
        feeds = NEWS_RSS_FEEDS

    signals: list[RawSignal] = []

    for source_id, feed_url in feeds.items():
        try:
            content = fetch(feed_url)
            parsed = feedparser.parse(content)
            for entry in parsed.entries:
                pub_date: datetime | None = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)

                signals.append(
                    RawSignal(
                        source_url=getattr(entry, "link", feed_url),
                        source_program=None,
                        source_type="rss",
                        title=getattr(entry, "title", None),
                        raw_content=getattr(entry, "summary", None)
                        or getattr(entry, "description", None),
                        fetched_at=pub_date or datetime.now(timezone.utc),
                        extra={"feed_source": source_id},
                    )
                )
            logger.info("RSS %s: %d entradas lidas", source_id, len(parsed.entries))
        except Exception as exc:
            logger.warning("Falha ao ler RSS %s (%s): %s", source_id, feed_url, exc)

    return signals
