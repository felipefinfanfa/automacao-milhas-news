"""Tier 3 — Novos subdomínios dos programas via DNS público."""
import logging
from datetime import datetime, timezone

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

_PROMO_PREFIXES = [
    "promocoes", "promo", "bonus", "transferencia", "campanha",
    "ofertas", "transfer", "pontos",
]


def _resolve(hostname: str) -> bool:
    try:
        import dns.resolver

        dns.resolver.resolve(hostname, "A")
        return True
    except Exception:
        return False


def scan_dns_monitor() -> list[RawSignal]:
    """Verifica se novos subdomínios de promoção estão ativos via DNS."""
    signals: list[RawSignal] = []

    for program in LOYALTY_PROGRAMS:
        domain = _DOMAIN_MAP.get(program)
        if not domain:
            continue

        for prefix in _PROMO_PREFIXES:
            hostname = f"{prefix}.{domain}"
            if _resolve(hostname):
                url = f"https://{hostname}/"
                logger.info("dns_monitor: %s resolveu para %s", hostname, program)
                signals.append(
                    RawSignal(
                        source_url=url,
                        source_program=program,
                        source_type="dns_monitor",
                        fetched_at=datetime.now(timezone.utc),
                        extra={"hostname": hostname},
                    )
                )

    return signals
