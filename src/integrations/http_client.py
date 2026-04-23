"""Ponto central para todas as requisições HTTP do projeto.

Regras:
- Domínios dos 6 programas → cloudscraper (bypass Cloudflare)
- Demais domínios (sitemaps, RSS, APIs públicas) → httpx
- Delay de 15-30s aleatório entre requisições ao mesmo domínio
- NUNCA paralelizar requisições ao mesmo domínio
- 429/403 → registrar blocked_until = now() + 2h
"""
import asyncio
import logging
import random
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import cloudscraper
import httpx

from src.config.settings import CLOUDSCRAPER_DOMAINS
from src.integrations.user_agents import get_current_ua

logger = logging.getLogger(__name__)

_domain_last_req: dict[str, float] = {}
_scraper: cloudscraper.CloudScraper | None = None


def _get_scraper() -> cloudscraper.CloudScraper:
    global _scraper
    if _scraper is None:
        _scraper = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "windows", "mobile": False}
        )
    return _scraper


def _extract_domain(url: str) -> str:
    parsed = urlparse(url)
    return parsed.netloc.lstrip("www.")


def _needs_cloudscraper(domain: str) -> bool:
    for cs_domain in CLOUDSCRAPER_DOMAINS:
        if domain.endswith(cs_domain):
            return True
    return False


def _wait_for_domain(domain: str) -> None:
    last = _domain_last_req.get(domain, 0.0)
    elapsed = time.monotonic() - last
    delay = random.uniform(15, 30)
    if elapsed < delay:
        sleep_time = delay - elapsed
        logger.debug("Aguardando %.1fs antes de requisição para %s", sleep_time, domain)
        time.sleep(sleep_time)
    _domain_last_req[domain] = time.monotonic()


def _check_blocked(domain: str) -> bool:
    """Consulta o DB para saber se o domínio está em cooldown. Retorna True se bloqueado."""
    try:
        from sqlalchemy import select, text

        from src.config.settings import settings
        from src.db.models import MonitorState, create_engine_from_url

        engine = create_engine_from_url(settings.database_url)
        with engine.connect() as conn:
            row = conn.execute(
                select(MonitorState).where(MonitorState.domain == domain)
            ).first()
            if row and row[0].blocked_until > datetime.now(timezone.utc):
                logger.warning(
                    "Domínio %s bloqueado até %s — pulando", domain, row[0].blocked_until
                )
                return True
    except Exception:
        pass
    return False


def _register_blocked(domain: str) -> None:
    """Registra blocked_until = now() + 2h no DB."""
    try:
        from sqlalchemy.dialects.postgresql import insert

        from src.config.settings import settings
        from src.db.models import MonitorState, create_engine_from_url

        blocked_until = datetime.now(timezone.utc) + timedelta(hours=2)
        engine = create_engine_from_url(settings.database_url)
        with engine.begin() as conn:
            stmt = insert(MonitorState).values(
                domain=domain, blocked_until=blocked_until
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["domain"],
                set_={"blocked_until": blocked_until, "updated_at": datetime.now(timezone.utc)},
            )
            conn.execute(stmt)
        logger.warning("Domínio %s marcado como bloqueado por 2h", domain)
    except Exception as exc:
        logger.error("Erro ao registrar bloqueio para %s: %s", domain, exc)


def fetch(url: str, timeout: int = 30) -> str:
    """Faz requisição HTTP síncrona respeitando delays e cooldowns.

    Retorna o conteúdo como texto. Lança httpx.HTTPStatusError ou
    cloudscraper.exceptions.CloudflareException em falha.
    """
    domain = _extract_domain(url)

    if _check_blocked(domain):
        raise RuntimeError(f"Domínio {domain} em cooldown")

    _wait_for_domain(domain)

    headers = {"User-Agent": get_current_ua()}

    if _needs_cloudscraper(domain):
        scraper = _get_scraper()
        scraper.headers.update(headers)
        try:
            resp = scraper.get(url, timeout=timeout)
            if resp.status_code in (429, 403):
                _register_blocked(domain)
                raise RuntimeError(f"HTTP {resp.status_code} de {domain}")
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            if hasattr(exc, "response") and getattr(exc.response, "status_code", None) in (429, 403):
                _register_blocked(domain)
            raise
    else:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as client:
            resp = client.get(url)
            if resp.status_code in (429, 403):
                _register_blocked(domain)
                raise httpx.HTTPStatusError(
                    f"HTTP {resp.status_code}", request=resp.request, response=resp
                )
            resp.raise_for_status()
            return resp.text


async def fetch_async(url: str, timeout: int = 30) -> str:
    """Versão assíncrona de fetch (executa em thread pool para não bloquear event loop)."""
    return await asyncio.get_event_loop().run_in_executor(None, fetch, url, timeout)
