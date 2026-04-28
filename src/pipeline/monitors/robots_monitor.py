"""Tier 2 — robots.txt dos programas.

Monitora novos caminhos no robots.txt que possam indicar novas seções de promoção.
"""

import logging
import re
from datetime import UTC, datetime
from urllib.parse import urlparse

from src.config.settings import PROGRAM_URLS
from src.tools.http_client import fetch
from src.types import RawSignal

logger = logging.getLogger(__name__)

_PROMO_PATH_RE = re.compile(r"/(?:promo|campa|bonus|bônus|transfer|oferta)", re.I)


def _robots_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}/robots.txt"


def _extract_disallowed_paths(content: str) -> list[str]:
    paths: list[str] = []
    for line in content.splitlines():
        line = line.strip()
        if line.lower().startswith("disallow:") or line.lower().startswith("allow:"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                path = parts[1].strip()
                if path and path != "/":
                    paths.append(path)
    return paths


def scan_robots(urls: dict[str, str] | None = None) -> list[RawSignal]:
    """Verifica robots.txt em busca de novas rotas de promoção."""
    if urls is None:
        urls = PROGRAM_URLS

    signals: list[RawSignal] = []

    for program, base_url in urls.items():
        robots_url = _robots_url(base_url)
        try:
            content = fetch(robots_url)
            paths = _extract_disallowed_paths(content)
            promo_paths = [p for p in paths if _PROMO_PATH_RE.search(p)]

            for path in promo_paths:
                parsed = urlparse(base_url)
                full_url = f"{parsed.scheme}://{parsed.netloc}{path}"
                signals.append(
                    RawSignal(
                        source_url=full_url,
                        source_program=program,
                        source_type="robots",
                        fetched_at=datetime.now(UTC),
                        extra={"robots_path": path},
                    )
                )
            logger.info(
                "robots.txt %s: %d caminhos de promo encontrados", program, len(promo_paths)
            )
        except Exception as exc:
            logger.debug("Falha ao ler robots.txt de %s: %s", program, exc)

    return signals
