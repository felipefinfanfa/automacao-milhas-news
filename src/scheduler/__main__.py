"""Entry point do scheduler: python -m src.scheduler

Cron de 6 horários/dia (06,09,12,15,18,21 BRT):
- 06h: Tier 3 (todos os monitores)
- 09h: Tier 2
- 12h: Tier 1 + envio de e-mail de rotina (force_send=True)
- 15h: Tier 1
- 18h: Tier 2
- 21h: Tier 1
"""
import argparse
import logging
import sys

import sentry_sdk
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config.settings import settings
from src.db.models import create_engine_from_url, get_session_factory

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.app_env)


def _make_session():
    engine = create_engine_from_url(settings.database_url)
    SessionFactory = get_session_factory(engine)
    return SessionFactory()


def _run_tier1_job(scheduler, dry_run=False, force_send=False):
    from src.scheduler.jobs.tier1 import run_tier1

    with _make_session() as session:
        try:
            run_tier1(session, scheduler=scheduler, dry_run=dry_run, force_send=force_send)
        except Exception as exc:
            logger.error("Erro no Tier 1 scan: %s", exc, exc_info=True)


def _run_tier2_job(scheduler, dry_run=False):
    from src.scheduler.jobs.tier2 import run_tier2

    with _make_session() as session:
        try:
            run_tier2(session, scheduler=scheduler, dry_run=dry_run)
        except Exception as exc:
            logger.error("Erro no Tier 2 scan: %s", exc, exc_info=True)


def _run_tier3_job(scheduler, dry_run=False):
    from src.scheduler.jobs.tier3 import run_tier3

    with _make_session() as session:
        try:
            run_tier3(session, scheduler=scheduler, dry_run=dry_run)
        except Exception as exc:
            logger.error("Erro no Tier 3 scan: %s", exc, exc_info=True)


def _check_db_alive():
    from sqlalchemy import text

    try:
        engine = create_engine_from_url(settings.database_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.debug("DB keepalive OK")
    except Exception as exc:
        logger.error("DB keepalive falhou: %s", exc)


def main(dry_run: bool = False) -> None:
    if dry_run:
        logger.info("[DRY RUN] Executando 1 ciclo completo Tier 3 sem e-mails")
        with _make_session() as session:
            from src.scheduler.jobs.tier3 import run_tier3
            run_tier3(session, dry_run=True)
        logger.info("[DRY RUN] Concluído")
        return

    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")

    tz = "America/Sao_Paulo"

    scheduler.add_job(
        _run_tier3_job, CronTrigger(hour=6, minute=0, timezone=tz),
        args=[scheduler], id="tier3_06h", name="Tier3 06h",
    )
    scheduler.add_job(
        _run_tier2_job, CronTrigger(hour=9, minute=0, timezone=tz),
        args=[scheduler], id="tier2_09h", name="Tier2 09h",
    )
    scheduler.add_job(
        _run_tier1_job, CronTrigger(hour=12, minute=0, timezone=tz),
        kwargs={"scheduler": scheduler, "force_send": True},
        id="tier1_12h", name="Tier1 12h (rotina)",
    )
    scheduler.add_job(
        _run_tier1_job, CronTrigger(hour=15, minute=0, timezone=tz),
        args=[scheduler], id="tier1_15h", name="Tier1 15h",
    )
    scheduler.add_job(
        _run_tier2_job, CronTrigger(hour=18, minute=0, timezone=tz),
        args=[scheduler], id="tier2_18h", name="Tier2 18h",
    )
    scheduler.add_job(
        _run_tier1_job, CronTrigger(hour=21, minute=0, timezone=tz),
        args=[scheduler], id="tier1_21h", name="Tier1 21h",
    )

    scheduler.add_job(
        _check_db_alive, CronTrigger(day="*/5", hour=3, minute=0, timezone=tz),
        id="db_keepalive", name="DB keepalive",
    )

    logger.info("Scheduler iniciado — 6 scans/dia (06,09,12,15,18,21 BRT)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler encerrado")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Miles Radar Scheduler")
    parser.add_argument("--dry-run", action="store_true", help="Executa 1 ciclo sem enviar e-mails")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
