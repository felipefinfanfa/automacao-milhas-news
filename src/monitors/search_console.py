"""Tier 2 — Google Search Console (opcional).

Stub inicial — implementar quando service account for configurada.
Ver docs/setup-search-console.md para instruções de setup.
"""
import logging

from src.types import RawSignal

logger = logging.getLogger(__name__)


def scan_search_console() -> list[RawSignal]:
    """Retorna queries de busca com cliques em URLs de promoção.

    Requer GOOGLE_SERVICE_ACCOUNT_JSON no .env e site verificado no GSC.
    """
    logger.debug("search_console: não configurado, pulando")
    return []
