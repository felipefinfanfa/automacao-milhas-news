"""Executa um scan completo e envia e-mail imediatamente.

Funciona sem preferências de usuário no DB — envia direto para DIGEST_RECIPIENT.
Usa Gmail SMTP se RESEND_API_KEY não estiver configurado.

Uso:
    python scripts/run_now.py
    python scripts/run_now.py --tier 1   # somente Tier 1 (mais rápido)
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

# Garante que src/ está no path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level="INFO",
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_now")


def main(tier: int = 1) -> None:
    from src.config.settings import settings
    from src.db.models import Promotion, create_engine_from_url, get_session_factory
    from src.pipeline.dedup import dedup_batch
    from src.pipeline.dispatcher import _render_template, send_email
    from src.pipeline.extractor import extract
    from src.tools.user_agents import rotate_ua

    logger.info("=== Miles Radar — run_now (Tier %d) ===", tier)
    logger.info("Destinatário: %s", settings.digest_recipient)

    rotate_ua()
    signals = []

    # Tier 1 — sempre
    from src.pipeline.monitors.direct_scraper import scan_all_programs
    from src.pipeline.monitors.google_news import scan_google_news
    from src.pipeline.monitors.hash_diff import scan_hash_diff
    from src.pipeline.monitors.rss_monitor import scan_rss

    logger.info("Coletando sinais Tier 1...")
    signals.extend(scan_rss())
    signals.extend(scan_google_news())
    signals.extend(scan_hash_diff())
    signals.extend(scan_all_programs())

    if tier >= 2:
        from src.pipeline.monitors.news_scraper import scan_all_news
        from src.pipeline.monitors.robots_monitor import scan_robots
        from src.pipeline.monitors.sitemap_monitor import scan_sitemap

        logger.info("Coletando sinais Tier 2...")
        signals.extend(scan_sitemap())
        signals.extend(scan_robots())
        signals.extend(scan_all_news())

    logger.info("Total de sinais coletados: %d", len(signals))

    raw_promos = []
    for signal in signals:
        raw_promos.extend(extract(signal))

    logger.info("Promoções extraídas antes de dedup: %d", len(raw_promos))

    if not raw_promos:
        logger.warning("Nenhuma promoção extraída. Verifique os monitores.")
        return

    engine = create_engine_from_url(settings.database_url)
    SessionFactory = get_session_factory(engine)

    with SessionFactory() as session:
        results = dedup_batch(session, raw_promos)
        new_promos = [data for data, is_new in results if is_new]
        logger.info("Promoções novas (após dedup): %d", len(new_promos))

        now = datetime.now(UTC)
        active_db = (
            session.query(Promotion)
            .filter(
                (Promotion.ends_at == None) | (Promotion.ends_at > now)  # noqa: E711
            )
            .order_by(Promotion.bonus_percent.desc().nullslast())
            .limit(20)
            .all()
        )

        new_fingerprints = {p.fingerprint for p in new_promos}
        new_db = [p for p in active_db if p.fingerprint in new_fingerprints]

        if not new_db and not active_db:
            logger.info("Sem promoções para enviar.")
            return

        promos_to_show = sorted(
            new_db or active_db[:5],
            key=lambda p: p.bonus_percent or 0,
            reverse=True,
        )
        best = promos_to_show[0] if promos_to_show and promos_to_show[0].bonus_percent else None

        html = _render_template(
            "day1.html",
            {
                "email_title": "Promoções de Milhas — Scan Manual",
                "header_title": 'Digest de <span style="color:#38bdf8">Promoções</span>',
                "new_promotions": promos_to_show,
                "best_promotion": best,
            },
        )

        n = len(promos_to_show)
        suffix = "ões" if n > 1 else "ão"
        subject = f"Miles Radar — {n} promo{suffix} de milhas"

        logger.info("Enviando e-mail para %s...", settings.digest_recipient)
        sent = send_email(settings.digest_recipient, subject, html)

        if sent:
            logger.info("✓ E-mail enviado com sucesso!")
        else:
            logger.error("✗ Falha ao enviar e-mail. Verifique Gmail/Resend no .env")
            sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Executa scan e envia e-mail imediatamente")
    parser.add_argument(
        "--tier", type=int, default=1, choices=[1, 2], help="Tier de monitores (default: 1)"
    )
    args = parser.parse_args()
    main(tier=args.tier)
