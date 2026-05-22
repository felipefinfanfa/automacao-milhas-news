"""Único monitor — RSS dos blogs de milhas + fetch do HTML completo dos artigos.

3 dos 5 feeds retornam apenas summary curto (~300-500 chars) no RSS. Para esses,
buscamos o HTML completo do artigo via seletores site-específicos.

Filtra para artigos publicados nas últimas 48h e cujo título contém palavras-chave
de promoção — reduz ruído sem fetch desnecessário.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

import feedparser
from bs4 import BeautifulSoup

from src.config.settings import NEWS_RSS_FEEDS
from src.tools.http_client import fetch
from src.types import RawSignal

logger = logging.getLogger(__name__)

_MAX_AGE_HOURS = 48
_MIN_CONTENT_CHARS = 1500

# Seletores site-específicos (descobertos via análise da estrutura HTML real).
# Ordem importa: primeiro selector que casar é usado, NUNCA o mais longo,
# para evitar capturar sidebars / posts relacionados.
_SITE_SELECTORS: dict[str, list[str]] = {
    "passageiro_de_primeira": [".left-content"],
    "melhores_destinos": ["article"],
    "pontos_pra_voar": ["article"],
    "mestre_das_milhas": [".entry-content", "article"],
    "melhores_cartoes": ["article"],
}
_FALLBACK_SELECTORS = [".entry-content", ".post-content", "article", "main"]

# Tags removidas antes de extrair texto (reduz ruído de navegação/sidebar).
_STRIP_TAGS = ["script", "style", "noscript", "iframe", "nav", "header", "footer", "aside"]

# Seletores CSS de blocos a remover ANTES de extrair texto. Crítico para sites
# cujo container principal engloba "Leia também" / posts relacionados — títulos
# de outras promoções poluem o texto e causam misclassification (ex.: artigo de
# acúmulo Esfera virar transfer_bonus +80% Esfera→Latam porque o footer mencionava
# essa outra promo).
_SITE_STRIP_SELECTORS: dict[str, list[str]] = {
    "passageiro_de_primeira": [".box-footer"],
}

_PROMO_TITLE_RE = re.compile(
    r"b[oô]nus|transfer|promo|milhas|pontos|smiles|livelo|azul|latam|esfera"
    r"|passagem|passagens|voos|emiss[ãa]o|resgate|cashback",
    re.I,
)


def _parse_pub_date(entry: Any) -> datetime | None:
    t = getattr(entry, "published_parsed", None)
    if t:
        return datetime(t[0], t[1], t[2], t[3], t[4], t[5], tzinfo=UTC)
    return None


def _rss_content(entry: Any) -> str:
    content_list = getattr(entry, "content", None)
    if content_list:
        val = content_list[0].get("value")
        if val:
            return str(val)
    return getattr(entry, "summary", "") or getattr(entry, "description", "") or ""


def _extract_article_text(html: str, source_id: str) -> str | None:
    """Extrai o body do artigo usando seletor site-específico (first match wins)."""
    soup = BeautifulSoup(html, "lxml")
    selectors = _SITE_SELECTORS.get(source_id, []) + _FALLBACK_SELECTORS
    site_noise = _SITE_STRIP_SELECTORS.get(source_id, [])
    for sel in selectors:
        el = soup.select_one(sel)
        if not el:
            continue
        for tag in el(_STRIP_TAGS):
            tag.decompose()
        for noise_sel in site_noise:
            for noise in el.select(noise_sel):
                noise.decompose()
        txt = el.get_text(separator=" ", strip=True)
        if len(txt) >= _MIN_CONTENT_CHARS:
            return txt
    return None


def _fetch_full_article(url: str, source_id: str) -> str | None:
    try:
        html = fetch(url)
        return _extract_article_text(html, source_id)
    except Exception as exc:
        logger.debug("Falha ao buscar artigo %s: %s", url, exc)
        return None


def scan_news(feeds: dict[str, str] | None = None) -> list[RawSignal]:
    """Lê os feeds RSS e retorna RawSignals com conteúdo do corpo do artigo."""
    if feeds is None:
        feeds = NEWS_RSS_FEEDS

    cutoff = datetime.now(UTC) - timedelta(hours=_MAX_AGE_HOURS)
    signals: list[RawSignal] = []

    for source_id, feed_url in feeds.items():
        try:
            feed_content = fetch(feed_url)
            parsed = feedparser.parse(feed_content)
        except Exception as exc:
            logger.warning("Falha RSS %s (%s): %s", source_id, feed_url, exc)
            continue

        recent = 0
        fetched_full = 0
        for entry in parsed.entries:
            pub_date = _parse_pub_date(entry)
            if pub_date and pub_date < cutoff:
                continue

            title = getattr(entry, "title", "") or ""
            url = getattr(entry, "link", feed_url)
            rss_text = _rss_content(entry)

            if not _PROMO_TITLE_RE.search(title + " " + rss_text[:500]):
                continue

            content = rss_text
            if len(content) < _MIN_CONTENT_CHARS:
                full = _fetch_full_article(url, source_id)
                if full:
                    content = full
                    fetched_full += 1

            signals.append(
                RawSignal(
                    source_url=url,
                    source_program=None,
                    source_type="rss",
                    title=title or None,
                    raw_content=content,
                    fetched_at=pub_date or datetime.now(UTC),
                    extra={"feed_source": source_id},
                )
            )
            recent += 1

        logger.info(
            "RSS %s: %d artigos recentes (%d c/ HTML completo)",
            source_id,
            recent,
            fetched_full,
        )

    return signals
