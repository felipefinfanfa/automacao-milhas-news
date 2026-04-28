"""Tier 3 — Executa apenas no scan das 06h BRT.

Monitores adicionais: visual_diff.
Combina com Tier 2 no mesmo pipeline.
"""

from __future__ import annotations

import logging
from typing import Any

from src.pipeline.dedup import dedup_batch
from src.pipeline.extractor import extract
from src.pipeline.monitors.visual_diff import scan_visual_diff
from src.scheduler.jobs.tier2 import run_tier2
from src.tools.user_agents import rotate_ua
from src.types import PromotionData

logger = logging.getLogger(__name__)


def run_tier3(
    session: Any,
    scheduler: Any | None = None,
    dry_run: bool = False,
    force_send: bool = False,
) -> list[PromotionData]:
    """Executa Tier 2 + monitores adicionais do Tier 3."""
    rotate_ua()
    logger.info("=== Tier 3 scan iniciado ===")

    tier2_new = run_tier2(session, scheduler, dry_run, force_send)

    signals = []
    signals.extend(scan_visual_diff())

    logger.info("Tier 3 extra: %d sinais adicionais coletados", len(signals))

    if not signals:
        return tier2_new

    raw_promos: list[PromotionData] = []
    for signal in signals:
        raw_promos.extend(extract(signal))

    if not raw_promos:
        return tier2_new

    dedup_results = dedup_batch(session, raw_promos)
    new_tier3 = [data for data, is_new in dedup_results if is_new]
    logger.info("Tier 3 extra: %d promoções novas", len(new_tier3))

    return tier2_new + new_tier3
