"""Tier 2 — Executa nos scans de 09h e 18h BRT.

Monitores adicionais: sitemap_monitor, robots_monitor, news_scraper, search_console.
Combina com Tier 1 no mesmo pipeline.
"""
from __future__ import annotations

import logging
from typing import Any

from src.integrations.user_agents import rotate_ua
from src.monitors.news_scraper import scan_all_news
from src.monitors.robots_monitor import scan_robots
from src.monitors.search_console import scan_search_console
from src.monitors.sitemap_monitor import scan_sitemap
from src.processor.dedup import dedup_batch
from src.processor.extractor import extract
from src.scheduler.jobs.tier1 import run_tier1
from src.types import PromotionData

logger = logging.getLogger(__name__)


def run_tier2(
    session: Any,
    scheduler: Any | None = None,
    dry_run: bool = False,
    force_send: bool = False,
) -> list[PromotionData]:
    """Executa Tier 1 + monitores adicionais do Tier 2."""
    rotate_ua()
    logger.info("=== Tier 2 scan iniciado ===")

    tier1_new = run_tier1(session, scheduler, dry_run, force_send)

    signals = []
    signals.extend(scan_sitemap())
    signals.extend(scan_robots())
    signals.extend(scan_all_news())
    signals.extend(scan_search_console())

    logger.info("Tier 2 extra: %d sinais adicionais coletados", len(signals))

    if not signals:
        return tier1_new

    raw_promos: list[PromotionData] = []
    for signal in signals:
        raw_promos.extend(extract(signal))

    if not raw_promos:
        return tier1_new

    dedup_results = dedup_batch(session, raw_promos)
    new_tier2 = [data for data, is_new in dedup_results if is_new]
    logger.info("Tier 2 extra: %d promoções novas", len(new_tier2))

    return tier1_new + new_tier2
