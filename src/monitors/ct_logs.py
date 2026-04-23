"""Tier 3 — Certificate Transparency via crt.sh.

Detecta novos subdomínios dos programas que possam indicar novas features/promoções.
"""
import logging
from datetime import datetime, timezone

import httpx

from src.config.settings import LOYALTY_PROGRAMS
from src.types import RawSignal

logger = logging.getLogger(__name__)

_DOMAIN_MAP: dict[str, str] = {
    "smiles": "smiles.com.br",
    "azul": "voeazul.com.br",
    "latam": "latam.com",
    "livelo": "livelo.com.br",
    "esfera": "esfera.com.vc",
    "iupp": "iupp.com.br",
}

_PROMO_SUBDOMAIN_RE = __import__("re").compile(r"promo|campa|bonus|offer|transfer", __import__("re").I)


def _fetch_crt_domains(domain: str) -> list[str]:
    url = f"https://crt.sh/?q=%25.{domain}&output=json"
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
            names: set[str] = set()
            for entry in data:
                for name in entry.get("name_value", "").split("\n"):
                    name = name.strip().lstrip("*.")
                    if name.endswith(domain):
                        names.add(name)
            return list(names)
    except Exception as exc:
        logger.warning("Falha ao consultar crt.sh para %s: %s", domain, exc)
        return []


def scan_ct_logs() -> list[RawSignal]:
    """Verifica novos subdomínios via Certificate Transparency."""
    signals: list[RawSignal] = []

    for program in LOYALTY_PROGRAMS:
        domain = _DOMAIN_MAP.get(program)
        if not domain:
            continue

        subdomains = _fetch_crt_domains(domain)
        promo_subs = [s for s in subdomains if _PROMO_SUBDOMAIN_RE.search(s)]

        for subdomain in promo_subs:
            url = f"https://{subdomain}/"
            signals.append(
                RawSignal(
                    source_url=url,
                    source_program=program,
                    source_type="ct_logs",
                    fetched_at=datetime.now(timezone.utc),
                    extra={"subdomain": subdomain, "root_domain": domain},
                )
            )
        if promo_subs:
            logger.info("ct_logs %s: %d subdomínios de promo encontrados", program, len(promo_subs))

    return signals
