"""Ponto central para todas as requisições HTTP do projeto."""

import asyncio
import logging
import random
import time
from urllib.parse import urlparse

import httpx

from src.tools.user_agents import get_current_ua

logger = logging.getLogger(__name__)

_domain_last_req: dict[str, float] = {}


def _extract_domain(url: str) -> str:
    return urlparse(url).netloc.lstrip("www.")


def _wait_for_domain(domain: str) -> None:
    last = _domain_last_req.get(domain, 0.0)
    elapsed = time.monotonic() - last
    delay = random.uniform(2, 5)
    if elapsed < delay:
        time.sleep(delay - elapsed)
    _domain_last_req[domain] = time.monotonic()


def fetch(url: str, timeout: int = 30) -> str:
    """Faz requisição HTTP síncrona com delay por domínio."""
    domain = _extract_domain(url)
    _wait_for_domain(domain)
    headers = {"User-Agent": get_current_ua()}
    with httpx.Client(headers=headers, follow_redirects=True, timeout=timeout) as client:
        resp = client.get(url)
        resp.raise_for_status()
        return resp.text


async def fetch_async(url: str, timeout: int = 30) -> str:
    return await asyncio.get_event_loop().run_in_executor(None, fetch, url, timeout)
