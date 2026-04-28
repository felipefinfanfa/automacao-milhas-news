"""Tier 2 — sitemap.xml dos programas."""

import logging
import re
from datetime import UTC, datetime
from xml.etree import ElementTree

from src.config.settings import PROGRAM_URLS
from src.tools.http_client import fetch
from src.types import RawSignal

logger = logging.getLogger(__name__)

_PROMO_URL_RE = re.compile(r"promo|campa|bonus|bônus|transfer", re.I)
_SITEMAP_PATHS = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap-promotions.xml"]


def _find_sitemap_url(base_url: str) -> str | None:
    for path in _SITEMAP_PATHS:
        from urllib.parse import urlparse

        parsed = urlparse(base_url)
        sitemap_url = f"{parsed.scheme}://{parsed.netloc}{path}"
        try:
            content = fetch(sitemap_url)
            if "<urlset" in content or "<sitemapindex" in content:
                return sitemap_url
        except Exception:
            continue
    return None


def _extract_urls_from_sitemap(content: str) -> list[str]:
    urls: list[str] = []
    try:
        root = ElementTree.fromstring(content)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        for loc in root.findall(".//sm:loc", ns):
            if loc.text:
                urls.append(loc.text.strip())
        if not urls:
            for loc in root.findall(".//{*}loc"):
                if loc.text:
                    urls.append(loc.text.strip())
    except ElementTree.ParseError as exc:
        logger.warning("Erro ao parsear sitemap XML: %s", exc)
    return urls


def scan_sitemap(urls: dict[str, str] | None = None) -> list[RawSignal]:
    """Verifica sitemaps dos programas em busca de novas URLs de promoção."""
    if urls is None:
        urls = PROGRAM_URLS

    signals: list[RawSignal] = []

    for program, base_url in urls.items():
        sitemap_url = _find_sitemap_url(base_url)
        if not sitemap_url:
            logger.debug("Nenhum sitemap encontrado para %s", program)
            continue

        try:
            content = fetch(sitemap_url)
            all_urls = _extract_urls_from_sitemap(content)
            promo_urls = [u for u in all_urls if _PROMO_URL_RE.search(u)]

            for promo_url in promo_urls:
                signals.append(
                    RawSignal(
                        source_url=promo_url,
                        source_program=program,
                        source_type="sitemap",
                        fetched_at=datetime.now(UTC),
                        extra={"sitemap_url": sitemap_url},
                    )
                )
            logger.info("Sitemap %s: %d URLs de promo encontradas", program, len(promo_urls))
        except Exception as exc:
            logger.warning("Falha ao processar sitemap de %s: %s", program, exc)

    return signals
