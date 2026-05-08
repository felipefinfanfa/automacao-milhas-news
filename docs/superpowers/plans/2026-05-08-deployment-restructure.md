# Deployment Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate automation to GitHub Actions, registration site to Vercel, keep Supabase — removing all Docker/VPS infrastructure in the process.

**Architecture:** GitHub Actions runs `scripts/run_pipeline.py --tier N` on 6 cron schedules per day. Vercel hosts the static registration frontend plus 5 Python serverless API handlers. Supabase remains unchanged plus a new `automation_logs` table. APScheduler, Playwright, and the 3-day email sequence are removed.

**Tech Stack:** Python 3.12, GitHub Actions (cron), Vercel Python serverless, Supabase/PostgreSQL, SQLAlchemy 2 + Alembic, Resend + Gmail SMTP, httpx, feedparser, cloudscraper, beautifulsoup4, Jinja2.

**Spec:** `docs/superpowers/specs/2026-05-08-deployment-restructure-design.md`

---

## File Map

**Delete:**
- `Dockerfile`
- `docker-stack.yml`
- `.dockerignore`
- `.github/workflows/deploy.yml`
- `src/scheduler/` (entire directory)
- `src/pipeline/monitors/visual_diff.py`
- `src/pipeline/sequence.py`
- `src/api/main.py`
- `src/api/routes/preferences.py`
- `src/api/static/` (contents moved to `public/`)
- `tests/unit/test_sequence.py`

**Modify:**
- `requirements.txt` — remove 8 deps
- `src/db/models.py` — add `AutomationLog` model
- `src/pipeline/dispatcher.py` — inline sequence functions, remove all APScheduler code
- `src/pipeline/preference_filter.py` — tighten active check (1 line)
- `CLAUDE.md` — rewrite deployment, structure, commands, critical rules sections

**Create:**
- `src/db/migrations/versions/008_add_automation_logs.py`
- `scripts/run_pipeline.py`
- `.github/workflows/pipeline-tier1.yml`
- `.github/workflows/pipeline-tier2.yml`
- `api/preferences/register.py`
- `api/preferences/slots.py`
- `api/preferences/programs/list.py`
- `api/preferences/[user_id].py`
- `api/unsubscribe/[token].py`
- `api/requirements.txt`
- `vercel.json`
- `public/` (rename from `src/api/static/`)

---

## Task 1: Remove Docker and VPS infrastructure

**Files:**
- Delete: `Dockerfile`, `docker-stack.yml`, `.dockerignore`, `.github/workflows/deploy.yml`

- [ ] **Step 1: Delete the four infrastructure files**

```bash
git rm Dockerfile docker-stack.yml .dockerignore .github/workflows/deploy.yml
```

Expected output: 4 files removed from tracking.

- [ ] **Step 2: Verify deletions**

```bash
git status
```

Expected: 4 deleted files staged, no new files.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove Docker and VPS deploy infrastructure"
```

---

## Task 2: Remove deprecated pipeline code

**Files:**
- Delete: `src/scheduler/` (entire directory), `src/pipeline/monitors/visual_diff.py`, `tests/unit/test_sequence.py`
- Note: `src/pipeline/sequence.py` is deleted in Task 5 (dispatcher.py imports it — delete together)

- [ ] **Step 1: Delete scheduler, visual_diff, and test_sequence**

```bash
git rm -r src/scheduler/ src/pipeline/monitors/visual_diff.py tests/unit/test_sequence.py
```

Expected: all listed files staged for deletion.

- [ ] **Step 2: Verify no import of visual_diff elsewhere**

```bash
grep -r "visual_diff" src/ --include="*.py"
```

Expected: no output (no remaining imports).

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove scheduler, visual_diff monitor, and deprecated sequence tests"
```

---

## Task 3: Update requirements.txt

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Write the cleaned requirements.txt**

Replace the full file with:

```
# Runtime
cloudscraper==1.2.71
httpx==0.27.0
beautifulsoup4==4.12.3
lxml==6.1.0
feedparser==6.0.11

# Data & validation
pydantic==2.13.3
pydantic-settings==2.14.0
email-validator==2.2.0

# Database
SQLAlchemy==2.0.49
alembic==1.13.1
psycopg2-binary==2.9.12

# Supabase
supabase==2.5.0

# Email
resend==2.0.0

# Observability
sentry-sdk==2.5.1

# Utilities
python-dotenv==1.0.1
dnspython==2.6.1
jinja2==3.1.4

# Dev / quality
ruff==0.4.7
mypy==1.10.0
pytest==8.2.2
pytest-asyncio==0.23.7
pytest-cov==5.0.0
pytest-mock==3.14.0
types-beautifulsoup4==4.12.0.20240511
```

Removed: `playwright`, `playwright-stealth`, `imagehash`, `Pillow`, `APScheduler`, `fastapi`, `uvicorn[standard]`, `python-multipart`, `itsdangerous`, `types-Pillow`.

- [ ] **Step 2: Verify the pipeline still installs correctly (dry run)**

```bash
pip install -r requirements.txt --dry-run 2>&1 | tail -5
```

Expected: no errors. (If pip dry-run is not available, skip — will be caught by CI.)

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: remove playwright, apscheduler, fastapi and other unused dependencies"
```

---

## Task 4: Add AutomationLog model to the database

**Files:**
- Modify: `src/db/models.py` — add `AutomationLog` class
- Create: `src/db/migrations/versions/008_add_automation_logs.py`

- [ ] **Step 1: Add AutomationLog to src/db/models.py**

After the `MonitorState` class (line 135) and before `get_session_factory`, add:

```python
class AutomationLog(Base):
    """Audit log for every GitHub Actions pipeline run."""

    __tablename__ = "automation_logs"

    id: Any = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_at: Any = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    workflow: Any = Column(Text, nullable=False)
    tier: Any = Column(Integer, nullable=False)
    status: Any = Column(Text, nullable=False)
    signals_found: Any = Column(Integer, default=0)
    promos_new: Any = Column(Integer, default=0)
    emails_sent: Any = Column(Integer, default=0)
    error_message: Any = Column(Text)
    error_traceback: Any = Column(Text)
    duration_seconds: Any = Column(Numeric(8, 2))
    gh_run_id: Any = Column(Text)
```

- [ ] **Step 2: Create migration 008**

Create `src/db/migrations/versions/008_add_automation_logs.py`:

```python
"""Add automation_logs table

Revision ID: 008
Revises: 007
Create Date: 2026-05-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automation_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("workflow", sa.Text, nullable=False),
        sa.Column("tier", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("signals_found", sa.Integer, server_default="0"),
        sa.Column("promos_new", sa.Integer, server_default="0"),
        sa.Column("emails_sent", sa.Integer, server_default="0"),
        sa.Column("error_message", sa.Text),
        sa.Column("error_traceback", sa.Text),
        sa.Column("duration_seconds", sa.Numeric(8, 2)),
        sa.Column("gh_run_id", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("automation_logs")
```

- [ ] **Step 3: Run the migration against Supabase**

```bash
alembic upgrade head
```

Expected output ends with: `Running upgrade 007 -> 008, Add automation_logs table`

- [ ] **Step 4: Verify the table was created**

```bash
python -c "
from src.db.models import AutomationLog, create_engine_from_url
from src.config.settings import settings
from sqlalchemy import inspect
e = create_engine_from_url(settings.database_url)
print(inspect(e).get_columns('automation_logs'))
"
```

Expected: list of column dicts including `id`, `workflow`, `tier`, `status`, etc.

- [ ] **Step 5: Commit**

```bash
git add src/db/models.py src/db/migrations/versions/008_add_automation_logs.py
git commit -m "feat: add AutomationLog model and migration 008"
```

---

## Task 5: Fix dispatcher.py — remove APScheduler, inline sequence functions

**Context:** `dispatcher.py` currently imports `has_sent` and `record_sent` from `sequence.py` (which we're deleting). It also contains 4 APScheduler-dependent functions that must go: `_send_followup_day`, `dispatch_upcoming`, `_schedule_pre_activation_reminder`, `_send_pre_activation_reminder`.

**Files:**
- Modify: `src/pipeline/dispatcher.py`
- Delete: `src/pipeline/sequence.py`

- [ ] **Step 1: Write the new dispatcher.py**

Replace the full file with:

```python
"""Dispatcher de e-mail: decide se/quando enviar, consolida por usuário.

Prioridade de envio: Resend (primary) → Gmail SMTP (fallback).
Nunca envia e-mail vazio ou para promoção expirada.
Múltiplas promoções novas no mesmo scan = 1 e-mail consolidado por usuário.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import UTC, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from src.config.settings import settings
from src.db.models import EmailLog

logger = logging.getLogger(__name__)

_TEMPLATES_DIR = Path(__file__).parent.parent / "email" / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)


# ---------------------------------------------------------------------------
# Email log helpers (inlined from the deleted sequence.py)
# ---------------------------------------------------------------------------

def has_sent(session: Any, user_id: str, promo_id: str, day_number: int) -> bool:
    """Returns True if the email for day N was already sent for this (user, promo)."""
    return (
        session.query(EmailLog)
        .filter_by(user_id=user_id, promo_id=promo_id, day_number=day_number)
        .first()
    ) is not None


def record_sent(session: Any, user_id: str, promo_id: str, day_number: int) -> None:
    """Records a successful send in email_log. Call only after a confirmed send."""
    log = EmailLog(
        user_id=user_id,
        promo_id=promo_id,
        day_number=day_number,
        sent_at=datetime.now(UTC),
    )
    session.add(log)
    session.commit()
    logger.debug(
        "email_log registrado: user=%s promo=%s day=%d",
        user_id[:8],
        str(promo_id)[:8],
        day_number,
    )


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

def _render_template(template_name: str, context: dict[str, Any]) -> str:
    now = datetime.now(UTC)
    context.setdefault("date_str", now.strftime("%A, %d de %B de %Y").lower())
    context.setdefault("unsubscribe_url", None)
    context.setdefault("manage_url", None)
    tpl = _jinja_env.get_template(template_name)
    return tpl.render(**context)


# ---------------------------------------------------------------------------
# Transport layer
# ---------------------------------------------------------------------------

def _send_via_resend(to: str, subject: str, html: str) -> bool:
    if not settings.resend_api_key:
        return False
    try:
        import resend

        resend.api_key = settings.resend_api_key
        resend.Emails.send(
            {
                "from": settings.email_from,
                "to": [to],
                "subject": subject,
                "html": html,
            }
        )
        logger.info("E-mail enviado via Resend para %s", to)
        return True
    except Exception as exc:
        logger.warning("Falha ao enviar via Resend: %s", exc)
        return False


def _send_via_gmail(to: str, subject: str, html: str) -> bool:
    if not settings.gmail_user or not settings.gmail_app_password:
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.gmail_user
        msg["To"] = to
        msg.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.gmail_user, settings.gmail_app_password)
            server.sendmail(settings.gmail_user, [to], msg.as_string())
        logger.info("E-mail enviado via Gmail SMTP para %s", to)
        return True
    except Exception as exc:
        logger.error("Falha ao enviar via Gmail: %s", exc)
        return False


def send_email(to: str, subject: str, html: str) -> bool:
    """Tries Resend first, falls back to Gmail SMTP."""
    return _send_via_resend(to, subject, html) or _send_via_gmail(to, subject, html)


# ---------------------------------------------------------------------------
# Dispatch functions
# ---------------------------------------------------------------------------

def _build_email_urls(user_id: str, unsubscribe_token: str | None) -> tuple[str | None, str]:
    unsubscribe_url = (
        f"{settings.app_base_url}/api/unsubscribe/{unsubscribe_token}"
        if unsubscribe_token
        else None
    )
    manage_url = f"{settings.app_base_url}/?user_id={user_id}"
    return unsubscribe_url, manage_url


def dispatch_confirmation(
    user_id: str,
    user_email: str,
    unsubscribe_token: str | None,
    transfer_pairs: list[Any],
    accumulation_programs: list[str],
) -> bool:
    """Sends confirmation email after user saves preferences."""
    unsubscribe_url, manage_url = _build_email_urls(user_id, unsubscribe_token)
    html = _render_template(
        "confirmation.html",
        {
            "email_title": "Preferências salvas — Radar de Milhas",
            "header_title": 'Prefer&ecirc;ncias <span style="color:#0891b2">Salvas</span>',
            "transfer_pairs": transfer_pairs,
            "accumulation_programs": accumulation_programs,
            "unsubscribe_url": unsubscribe_url,
            "manage_url": manage_url,
        },
    )
    sent = send_email(user_email, "Radar de Milhas — Preferências salvas", html)
    if sent:
        logger.info("E-mail de confirmação enviado para %s", user_email)
    return sent


def dispatch_day1(
    session: Any,
    user_id: str,
    user_email: str,
    new_promos: list[Any],
    unsubscribe_token: str | None = None,
) -> bool:
    """Sends consolidated Day 1 email to a user.

    Args:
        new_promos: active promos not yet sent to this user (already preference-filtered).

    Returns:
        True if the email was sent successfully.
    """
    now = datetime.now(UTC)

    promos_to_send = [
        p
        for p in new_promos
        if not has_sent(session, user_id, str(p.id), 1)
        and p.ends_at is not None
        and p.ends_at > now
    ]

    if not promos_to_send:
        logger.debug("Nenhuma promo nova para user=%s", user_id[:8])
        return False

    sorted_promos = sorted(promos_to_send, key=lambda p: p.bonus_percent or 0, reverse=True)
    transfer_promos = [p for p in sorted_promos if p.promo_type == "transfer_bonus"]
    accum_promos = [p for p in sorted_promos if p.promo_type != "transfer_bonus"]

    unsubscribe_url, manage_url = _build_email_urls(user_id, unsubscribe_token)

    html = _render_template(
        "day1.html",
        {
            "email_title": "Promoções para Você — Radar de Milhas",
            "header_title": 'Promoções <span style="color:#0891b2">para Você</span>',
            "transfer_promos": transfer_promos,
            "accum_promos": accum_promos,
            "unsubscribe_url": unsubscribe_url,
            "manage_url": manage_url,
        },
    )

    n = len(promos_to_send)
    subject = (
        f"Radar de Milhas — {n} nova{'s' if n > 1 else ''} "
        f"promoção{'ões' if n > 1 else ''} pra você"
    )
    sent = send_email(user_email, subject, html)

    if sent:
        for promo in promos_to_send:
            record_sent(session, user_id, str(promo.id), 1)

    return sent
```

- [ ] **Step 2: Delete sequence.py**

```bash
git rm src/pipeline/sequence.py
```

- [ ] **Step 3: Run the existing dispatcher tests**

```bash
pytest tests/unit/ -v -k "not test_sequence" 2>&1 | tail -20
```

Expected: no import errors, existing tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/pipeline/dispatcher.py
git commit -m "refactor: remove APScheduler from dispatcher, inline sequence helpers, drop sequence.py"
```

---

## Task 6: Fix preference_filter.py active check

**Context:** Line 48 currently allows promotions with `ends_at is None` through the active filter. The extractor already discards such promotions, but this defensive fix ensures the filter is correct regardless of how it is called.

**Files:**
- Modify: `src/pipeline/preference_filter.py:48`
- Modify: `tests/unit/test_preference_filter.py` — update/add test

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_preference_filter.py`, add to the existing test file:

```python
def test_filter_excludes_promos_with_null_ends_at(mock_session):
    from datetime import UTC, datetime, timedelta
    from src.pipeline.preference_filter import filter_for_user
    from src.pipeline.preference_filter import UserPreferencesData, PromotionData, TransferPair

    prefs = UserPreferencesData(
        user_id="user-1",
        email="u@example.com",
        transfer_pairs=[TransferPair(source="esfera", dest="smiles")],
        accumulation_programs=[],
    )
    promo_no_end = PromotionData(
        fingerprint="fp1",
        source_program="esfera",
        source_type="rss",
        source_url="http://x.com",
        promo_type="transfer_bonus",
        origin_program="esfera",
        destination_program="smiles",
        bonus_percent=100.0,
        ends_at=None,  # must be excluded
    )
    promo_active = PromotionData(
        fingerprint="fp2",
        source_program="esfera",
        source_type="rss",
        source_url="http://x.com",
        promo_type="transfer_bonus",
        origin_program="esfera",
        destination_program="smiles",
        bonus_percent=80.0,
        ends_at=datetime.now(UTC) + timedelta(days=7),
    )
    result = filter_for_user([promo_no_end, promo_active], prefs)
    assert len(result) == 1
    assert result[0].fingerprint == "fp2"
```

- [ ] **Step 2: Run to confirm it fails**

```bash
pytest tests/unit/test_preference_filter.py::test_filter_excludes_promos_with_null_ends_at -v
```

Expected: FAIL — the promo with `ends_at=None` passes through because of `p.ends_at is None or p.ends_at > now`.

- [ ] **Step 3: Fix the filter in preference_filter.py:48**

Change line 48 in `src/pipeline/preference_filter.py` from:
```python
    active = [p for p in promos if p.ends_at is None or p.ends_at > now]
```
to:
```python
    active = [p for p in promos if p.ends_at is not None and p.ends_at > now]
```

- [ ] **Step 4: Run the test to confirm it passes**

```bash
pytest tests/unit/test_preference_filter.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/preference_filter.py tests/unit/test_preference_filter.py
git commit -m "fix: exclude promotions with null ends_at from active filter"
```

---

## Task 7: Create scripts/run_pipeline.py

**Context:** This replaces `src/scheduler/` entirely. It is the entry point called by GitHub Actions. It runs monitors → extract → dedup → preference filter → dispatch, writes a record to `automation_logs`, and posts a Slack alert on unhandled exceptions.

**Files:**
- Create: `scripts/run_pipeline.py`

- [ ] **Step 1: Create the script**

```python
#!/usr/bin/env python3
"""Entry point for GitHub Actions: runs the full pipeline for the given tier.

Usage:
    python scripts/run_pipeline.py --tier 1
    python scripts/run_pipeline.py --tier 2
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import traceback
from datetime import UTC, datetime
from typing import Any

import httpx
import sentry_sdk

from src.config.settings import ACCUMULATION_PROGRAMS, VALID_TRANSFER_PAIRS, settings
from src.db.models import AutomationLog, EmailLog, Promotion, create_engine_from_url, get_session_factory
from src.pipeline.dedup import dedup_batch
from src.pipeline.dispatcher import dispatch_day1
from src.pipeline.extractor import extract
from src.pipeline.preference_filter import load_all_preferences
from src.tools.user_agents import rotate_ua
from src.types import PromotionData, UserPreferencesData

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.app_env)


def _send_slack_alert(tier: int, error_msg: str) -> None:
    webhook = os.getenv("SLACK_WEBHOOK_URL", "")
    if not webhook:
        return
    run_id = os.getenv("GITHUB_RUN_ID", "")
    run_url = (
        f"https://github.com/felipefinfanfa/radar-de-milhas/actions/runs/{run_id}"
        if run_id
        else "N/A"
    )
    payload = {
        "text": (
            f"❌ *Radar de Milhas — Pipeline Error*\n"
            f"Tier: {tier} | Run: <{run_url}|#{run_id}>\n"
            f"Error: {error_msg[:400]}"
        )
    }
    try:
        httpx.post(webhook, json=payload, timeout=10)
    except Exception:
        pass


def _run_monitors(tier: int) -> list[Any]:
    from src.pipeline.monitors.direct_scraper import scan_all_programs
    from src.pipeline.monitors.google_news import scan_google_news
    from src.pipeline.monitors.hash_diff import scan_hash_diff
    from src.pipeline.monitors.rss_monitor import scan_rss

    rotate_ua()
    signals: list[Any] = []
    signals.extend(scan_rss())
    signals.extend(scan_google_news())
    signals.extend(scan_hash_diff())
    signals.extend(scan_all_programs())

    if tier >= 2:
        from src.pipeline.monitors.news_scraper import scan_all_news
        from src.pipeline.monitors.robots_monitor import scan_robots
        from src.pipeline.monitors.sitemap_monitor import scan_sitemap

        signals.extend(scan_sitemap())
        signals.extend(scan_robots())
        signals.extend(scan_all_news())

    return signals


def _is_relevant_promo(promo: PromotionData) -> bool:
    if promo.promo_type == "transfer_bonus":
        origin = (promo.origin_program or promo.source_program or "").lower()
        dest = (promo.destination_program or "").lower()
        return (origin, dest) in VALID_TRANSFER_PAIRS
    program = (promo.origin_program or promo.source_program or "").lower()
    return program in ACCUMULATION_PROGRAMS


def _db_promo_matches_prefs(promo: Any, prefs: UserPreferencesData) -> bool:
    if promo.promo_type == "transfer_bonus":
        if not prefs.transfer_pairs:
            return False
        origin = (promo.origin_program or promo.source_program or "").lower()
        dest = (promo.destination_program or "").lower()
        return any(
            p.source.lower() == origin and p.dest.lower() == dest
            for p in prefs.transfer_pairs
        )
    program = (promo.origin_program or promo.source_program or "").lower()
    return program in {p.lower() for p in prefs.accumulation_programs}


def _dispatch_emails(session: Any) -> int:
    now = datetime.now(UTC)
    all_prefs = load_all_preferences(session)

    if not all_prefs:
        logger.warning("Nenhuma preferência cadastrada, sem e-mails")
        return 0

    all_active_db: list[Any] = (
        session.query(Promotion)
        .filter(
            Promotion.ends_at.isnot(None),
            Promotion.ends_at > now,
            Promotion.bonus_percent.isnot(None),
            (Promotion.starts_at == None) | (Promotion.starts_at <= now),  # noqa: E711
        )
        .order_by(Promotion.bonus_percent.desc().nullslast())
        .all()
    )

    emails_sent = 0
    for prefs in all_prefs:
        user_email = prefs.email or settings.digest_recipient
        sent_ids = {
            str(row.promo_id)
            for row in session.query(EmailLog.promo_id)
            .filter(EmailLog.user_id == prefs.user_id, EmailLog.day_number == 1)
            .all()
        }
        user_active = [
            p
            for p in all_active_db
            if str(p.id) not in sent_ids and _db_promo_matches_prefs(p, prefs)
        ]
        if user_active:
            sent = dispatch_day1(
                session=session,
                user_id=prefs.user_id,
                user_email=user_email,
                new_promos=user_active,
                unsubscribe_token=prefs.unsubscribe_token,
            )
            if sent:
                emails_sent += 1

    return emails_sent


def main(tier: int) -> None:
    started = time.monotonic()
    engine = create_engine_from_url(settings.database_url)
    SessionFactory = get_session_factory(engine)
    workflow = f"pipeline-tier{tier}"
    gh_run_id = os.getenv("GITHUB_RUN_ID")

    signals_found = promos_new = emails_sent = 0

    try:
        signals = _run_monitors(tier)
        signals_found = len(signals)
        logger.info("Tier %d: %d sinais coletados", tier, signals_found)

        raw_promos: list[PromotionData] = []
        for signal in signals:
            raw_promos.extend(extract(signal))
        raw_promos = [p for p in raw_promos if _is_relevant_promo(p)]
        logger.info("Tier %d: %d promoções relevantes extraídas", tier, len(raw_promos))

        with SessionFactory() as session:
            dedup_results = dedup_batch(session, raw_promos) if raw_promos else []
            new_promos_data = [data for data, is_new in dedup_results if is_new]
            promos_new = len(new_promos_data)
            logger.info("Tier %d: %d promoções novas após dedup", tier, promos_new)

            emails_sent = _dispatch_emails(session)
            logger.info("Tier %d: %d e-mails enviados", tier, emails_sent)

        duration = round(time.monotonic() - started, 2)
        with SessionFactory() as session:
            session.add(AutomationLog(
                workflow=workflow,
                tier=tier,
                status="success",
                signals_found=signals_found,
                promos_new=promos_new,
                emails_sent=emails_sent,
                duration_seconds=duration,
                gh_run_id=gh_run_id,
            ))
            session.commit()
        logger.info("Tier %d completo em %.1fs", tier, duration)

    except Exception as exc:
        duration = round(time.monotonic() - started, 2)
        tb = traceback.format_exc()
        error_msg = f"{type(exc).__name__}: {exc}"
        logger.error("Tier %d falhou: %s", tier, error_msg, exc_info=True)
        try:
            with SessionFactory() as session:
                session.add(AutomationLog(
                    workflow=workflow,
                    tier=tier,
                    status="error",
                    signals_found=signals_found,
                    promos_new=promos_new,
                    emails_sent=emails_sent,
                    duration_seconds=duration,
                    error_message=error_msg[:2000],
                    error_traceback=tb[:5000],
                    gh_run_id=gh_run_id,
                ))
                session.commit()
        except Exception:
            pass
        _send_slack_alert(tier, error_msg)
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Radar de Milhas pipeline runner")
    parser.add_argument("--tier", type=int, choices=[1, 2], default=1, help="Monitor tier to run")
    args = parser.parse_args()
    main(args.tier)
```

- [ ] **Step 2: Verify the script runs without import errors (dry check)**

```bash
python -c "import scripts.run_pipeline" 2>&1
```

Expected: no output (no import errors). If `scripts` is not a package, run:
```bash
python -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('run_pipeline', 'scripts/run_pipeline.py')
mod = importlib.util.module_from_spec(spec)
" 2>&1
```

Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add scripts/run_pipeline.py
git commit -m "feat: add run_pipeline.py as GitHub Actions entry point with automation logging and Slack alerts"
```

---

## Task 8: Create GitHub Actions workflow files

**Files:**
- Create: `.github/workflows/pipeline-tier1.yml`
- Create: `.github/workflows/pipeline-tier2.yml`

- [ ] **Step 1: Create pipeline-tier1.yml**

```yaml
name: Pipeline — Tier 1

on:
  schedule:
    - cron: '0 12 * * *'   # 09:00 BRT (UTC-3)
    - cron: '0 15 * * *'   # 12:00 BRT
    - cron: '0 18 * * *'   # 15:00 BRT
    - cron: '0 0 * * *'    # 21:00 BRT
  workflow_dispatch:
    inputs:
      tier:
        description: 'Tier to run (1 or 2)'
        required: false
        default: '1'

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run pipeline tier 1
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          DIGEST_RECIPIENT: ${{ secrets.DIGEST_RECIPIENT }}
          SENTRY_DSN: ${{ secrets.SENTRY_DSN }}
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
          APP_ENV: production
        run: python scripts/run_pipeline.py --tier 1
```

- [ ] **Step 2: Create pipeline-tier2.yml**

```yaml
name: Pipeline — Tier 2

on:
  schedule:
    - cron: '0 9 * * *'    # 06:00 BRT (UTC-3)
    - cron: '0 21 * * *'   # 18:00 BRT
  workflow_dispatch:

jobs:
  run:
    runs-on: ubuntu-latest
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run pipeline tier 2
        env:
          DATABASE_URL: ${{ secrets.DATABASE_URL }}
          RESEND_API_KEY: ${{ secrets.RESEND_API_KEY }}
          GMAIL_USER: ${{ secrets.GMAIL_USER }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
          DIGEST_RECIPIENT: ${{ secrets.DIGEST_RECIPIENT }}
          SENTRY_DSN: ${{ secrets.SENTRY_DSN }}
          SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
          APP_ENV: production
        run: python scripts/run_pipeline.py --tier 2
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/pipeline-tier1.yml .github/workflows/pipeline-tier2.yml
git commit -m "feat: add GitHub Actions pipeline workflows for tier 1 and tier 2"
```

---

## Task 9: Move static frontend to public/

**Context:** Vercel serves `public/` as the static root. The current `src/api/static/` contains the registration site.

**Files:**
- Rename: `src/api/static/` → `public/`

- [ ] **Step 1: Move the directory**

```bash
git mv src/api/static public
```

- [ ] **Step 2: Verify the move**

```bash
ls public/
```

Expected: `index.html`, `assets/`, `css/`, `js/` (or whichever subdirectories exist).

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor: move src/api/static to public/ for Vercel static hosting"
```

---

## Task 10: Create Vercel API handlers

**Context:** 5 Python serverless functions replacing the FastAPI routes. Each uses `http.server.BaseHTTPRequestHandler`. They reuse `src/db/models.py`, `src/config/settings.py`, and `src/pipeline/dispatcher.py` (for confirmation email). The Pydantic schemas in `src/api/schemas/preferences.py` are kept and reused.

**Files:**
- Create: `api/preferences/register.py`, `api/preferences/slots.py`, `api/preferences/programs/list.py`, `api/preferences/[user_id].py`, `api/unsubscribe/[token].py`

- [ ] **Step 1: Create api/preferences/register.py**

```python
"""POST /api/preferences/register — create or retrieve a user account."""

import json
import uuid
from http.server import BaseHTTPRequestHandler
from typing import Any

from src.config.settings import settings
from src.db.models import UserPreferences, create_engine_from_url, get_session_factory

_engine = create_engine_from_url(settings.database_url)
_SessionFactory = get_session_factory(_engine)


def _json_response(handler: Any, status: int, data: dict) -> None:
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            name = str(body.get("name", "")).strip()
            email = str(body.get("email", "")).strip().lower()
            phone = str(body.get("phone", "")).strip()

            if not name or not email or not phone:
                _json_response(self, 400, {"detail": "name, email e phone são obrigatórios"})
                return

            with _SessionFactory() as session:
                row = session.query(UserPreferences).filter_by(email=email).first()
                if row:
                    _json_response(self, 200, {
                        "user_id": str(row.user_id),
                        "email": email,
                        "name": row.name,
                        "phone": row.phone,
                        "is_new": False,
                    })
                    return

                count = session.query(UserPreferences).count()
                if count >= settings.max_users:
                    _json_response(self, 400, {
                        "detail": "Número máximo de cadastros atingido. Tente novamente mais tarde."
                    })
                    return

                new_id = uuid.uuid4()
                row = UserPreferences(
                    user_id=new_id,
                    email=email,
                    name=name,
                    phone=phone,
                    unsubscribe_token=uuid.uuid4(),
                    monitored_programs=[],
                    transfer_pairs=[],
                    accumulation_programs=[],
                )
                session.add(row)
                session.commit()
                _json_response(self, 201, {
                    "user_id": str(new_id),
                    "email": email,
                    "name": name,
                    "phone": phone,
                    "is_new": True,
                })
        except json.JSONDecodeError:
            _json_response(self, 400, {"detail": "JSON inválido"})
        except Exception as exc:
            _json_response(self, 500, {"detail": str(exc)})
```

- [ ] **Step 2: Create api/preferences/slots.py**

```python
"""GET /api/preferences/slots — available registration slots."""

import json
from http.server import BaseHTTPRequestHandler
from typing import Any

from src.config.settings import settings
from src.db.models import UserPreferences, create_engine_from_url, get_session_factory

_engine = create_engine_from_url(settings.database_url)
_SessionFactory = get_session_factory(_engine)


def _json_response(handler: Any, status: int, data: dict) -> None:
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            with _SessionFactory() as session:
                used = session.query(UserPreferences).count()
            total = settings.max_users
            _json_response(self, 200, {
                "used": used,
                "total": total,
                "remaining": max(0, total - used),
            })
        except Exception as exc:
            _json_response(self, 500, {"detail": str(exc)})
```

- [ ] **Step 3: Create api/preferences/programs/list.py**

```python
"""GET /api/preferences/programs/list — list of loyalty programs."""

import json
from http.server import BaseHTTPRequestHandler
from typing import Any

from src.config.settings import LOYALTY_PROGRAMS


def _json_response(handler: Any, status: int, data: dict) -> None:
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        _json_response(self, 200, {"programs": LOYALTY_PROGRAMS})
```

- [ ] **Step 4: Create api/preferences/[user_id].py**

```python
"""GET + PUT /api/preferences/[user_id] — read and update user preferences."""

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler
from typing import Any

from src.api.schemas.preferences import UserPreferencesIn
from src.config.settings import settings
from src.db.models import UserPreferences, create_engine_from_url, get_session_factory

_engine = create_engine_from_url(settings.database_url)
_SessionFactory = get_session_factory(_engine)


def _json_response(handler: Any, status: int, data: dict) -> None:
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _row_to_dict(row: Any) -> dict:
    return {
        "user_id": str(row.user_id),
        "email": row.email,
        "name": row.name,
        "phone": row.phone,
        "monitored_programs": row.monitored_programs or [],
        "transfer_pairs": row.transfer_pairs or [],
        "accumulation_programs": row.accumulation_programs or [],
    }


def _parse_user_id(path: str) -> str:
    return path.split("?")[0].rstrip("/").split("/")[-1]


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        user_id = _parse_user_id(self.path)
        try:
            with _SessionFactory() as session:
                row = session.query(UserPreferences).filter_by(user_id=user_id).first()
            if not row:
                _json_response(self, 404, {"detail": "Preferências não encontradas"})
                return
            _json_response(self, 200, _row_to_dict(row))
        except Exception as exc:
            _json_response(self, 500, {"detail": str(exc)})

    def do_PUT(self):
        user_id = _parse_user_id(self.path)
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            prefs_in = UserPreferencesIn(**body)
            valid_pairs = prefs_in.validated_transfer_pairs()
            pairs = [{"source": p.source, "dest": p.dest} for p in valid_pairs]

            with _SessionFactory() as session:
                row = session.query(UserPreferences).filter_by(user_id=user_id).first()
                if row:
                    row.monitored_programs = prefs_in.validated_programs()
                    row.transfer_pairs = pairs
                    row.accumulation_programs = prefs_in.validated_accumulation()
                else:
                    row = UserPreferences(
                        user_id=uuid.UUID(user_id),
                        monitored_programs=prefs_in.validated_programs(),
                        transfer_pairs=pairs,
                        accumulation_programs=prefs_in.validated_accumulation(),
                    )
                    session.add(row)
                session.commit()
                session.refresh(row)
                result = _row_to_dict(row)
                has_prefs = bool(row.transfer_pairs or row.accumulation_programs)
                send_confirmation = has_prefs and row.email
                token = str(row.unsubscribe_token) if row.unsubscribe_token else None
                uid = str(row.user_id)
                email = row.email
                acc_programs = row.accumulation_programs or []
                pair_objs = [
                    type("P", (), {"source": p["source"], "dest": p["dest"]})()
                    for p in (row.transfer_pairs or [])
                    if "source" in p and "dest" in p
                ]

            if send_confirmation:
                from src.pipeline.dispatcher import dispatch_confirmation
                threading.Thread(
                    target=dispatch_confirmation,
                    kwargs={
                        "user_id": uid,
                        "user_email": email,
                        "unsubscribe_token": token,
                        "transfer_pairs": pair_objs,
                        "accumulation_programs": acc_programs,
                    },
                    daemon=True,
                ).start()

            _json_response(self, 200, result)
        except json.JSONDecodeError:
            _json_response(self, 400, {"detail": "JSON inválido"})
        except Exception as exc:
            _json_response(self, 500, {"detail": str(exc)})
```

- [ ] **Step 5: Create api/unsubscribe/[token].py**

```python
"""GET /api/unsubscribe/[token] — unsubscribe and delete user data."""

import html as html_module
import uuid
from http.server import BaseHTTPRequestHandler
from textwrap import dedent
from typing import Any

from src.db.models import UserPreferences, create_engine_from_url, get_session_factory
from src.config.settings import settings

_engine = create_engine_from_url(settings.database_url)
_SessionFactory = get_session_factory(_engine)


def _unsubscribe_html(message: str) -> bytes:
    content = dedent(f"""\
        <!DOCTYPE html>
        <html lang="pt-BR">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width,initial-scale=1">
          <title>Radar de Milhas — Cancelar inscrição</title>
          <style>
            body {{
              font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
              background: #f1f5f9; display: flex; align-items: center;
              justify-content: center; min-height: 100vh; margin: 0;
            }}
            .card {{
              background: white; border-radius: 12px; padding: 2rem 2.5rem;
              box-shadow: 0 4px 24px rgba(15,23,42,.1); max-width: 420px;
              text-align: center;
            }}
            h1 {{ font-size: 1.25rem; color: #0f172a; margin-bottom: .75rem; }}
            p  {{ color: #64748b; font-size: .9375rem; line-height: 1.6; }}
            a  {{ color: #6366f1; font-weight: 600; }}
          </style>
        </head>
        <body>
          <div class="card">
            <h1>Radar de Milhas</h1>
            <p>{html_module.escape(message)}</p>
            <p style="margin-top:1.25rem"><a href="/">Voltar ao site</a></p>
          </div>
        </body>
        </html>
    """)
    return content.encode()


def _html_response(handler: Any, status: int, body: bytes) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        token_str = self.path.split("?")[0].rstrip("/").split("/")[-1]
        try:
            token_uuid = uuid.UUID(token_str)
        except ValueError:
            _html_response(self, 404, _unsubscribe_html("Token inválido."))
            return

        try:
            with _SessionFactory() as session:
                row = session.query(UserPreferences).filter_by(
                    unsubscribe_token=token_uuid
                ).first()
                if not row:
                    _html_response(
                        self, 404,
                        _unsubscribe_html("Usuário não encontrado ou já removido.")
                    )
                    return
                session.delete(row)
                session.commit()
            _html_response(
                self, 200,
                _unsubscribe_html(
                    "Inscrição cancelada com sucesso. "
                    "Seus dados foram permanentemente removidos."
                ),
            )
        except Exception as exc:
            _html_response(self, 500, _unsubscribe_html(f"Erro interno: {exc}"))
```

- [ ] **Step 6: Commit**

```bash
git add api/
git commit -m "feat: add Vercel serverless handlers for preferences and unsubscribe routes"
```

---

## Task 11: Create vercel.json and api/requirements.txt

**Files:**
- Create: `vercel.json`
- Create: `api/requirements.txt`

- [ ] **Step 1: Create vercel.json**

```json
{
  "version": 2,
  "rewrites": [
    { "source": "/api/(.*)", "destination": "/api/$1" }
  ]
}
```

- [ ] **Step 2: Create api/requirements.txt**

This file is picked up by Vercel for Python serverless functions in `api/`:

```
pydantic==2.13.3
pydantic-settings==2.14.0
email-validator==2.2.0
SQLAlchemy==2.0.49
psycopg2-binary==2.9.12
resend==2.0.0
httpx==0.27.0
jinja2==3.1.4
python-dotenv==1.0.1
dnspython==2.6.1
sentry-sdk==2.5.1
```

- [ ] **Step 3: Commit**

```bash
git add vercel.json api/requirements.txt
git commit -m "feat: add vercel.json and api/requirements.txt for Vercel deployment"
```

---

## Task 12: Remove old API files

**Files:**
- Delete: `src/api/main.py`, `src/api/routes/preferences.py`

- [ ] **Step 1: Delete the FastAPI files**

```bash
git rm src/api/main.py src/api/routes/preferences.py
```

- [ ] **Step 2: Verify no remaining imports of the deleted modules**

```bash
grep -r "from src.api.main\|from src.api.routes\|import src.api.main\|import src.api.routes" . --include="*.py"
```

Expected: no output.

- [ ] **Step 3: Run the full test suite to catch regressions**

```bash
pytest tests/unit/ -v 2>&1 | tail -30
```

Expected: all tests pass. No import errors.

- [ ] **Step 4: Run quality checks**

```bash
ruff check . && ruff format --check .
```

Expected: no errors. If there are formatting issues, run `ruff format .` and re-commit.

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "chore: remove FastAPI app and routes (replaced by Vercel handlers)"
```

---

## Task 13: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Rewrite CLAUDE.md**

Replace the full file with:

```markdown
# Miles Radar — CLAUDE.md

> Read this file at the start of every session. Keep it updated as the project evolves.

---

## 1. Project

**What it does:** Monitors transfer and accumulation promotions across Brazilian miles programs (Smiles, Azul, LATAM, Livelo, Esfera) and sends an immediate email alert for every new promotion detected. Target operational cost: zero (except hosting).

**Trigger:** Cron via GitHub Actions at 6 times/day (06h, 09h, 12h, 15h, 18h, 21h BRT). Email sent whenever a new active promotion is detected — no routine digest.

**Output:** Consolidated email per user with active promotions matching their preferences.

**Criticality:** Medium — up to 1h delay is acceptable.

---

## 2. Automation Mode

### MODE A — Deterministic Pipeline

**Flow:**
```
[GitHub Actions Cron] → [Monitors] → [Extractor] → [Dedup] → [Preference Filter] → [Email Dispatcher]
```

Monitors run sequentially by tier. Each step is a deterministic function. No agent, no memory, no complex state.

---

## 3. Stack

**Runtime:** Python 3.12

**Dependencies:**
- `cloudscraper` — Cloudflare bypass for program sites
- `httpx` — async HTTP for RSS, sitemaps and public APIs
- `beautifulsoup4` + `lxml` + `feedparser` — HTML and RSS parsing
- `pydantic v2` — schema validation
- `sqlalchemy 2` + `alembic` — ORM and migrations
- `supabase-py` — user auth
- `jinja2` — email templates

**Integrations:**
- Programs: Smiles, Azul, LATAM, Livelo, Esfera — no auth
- News: Melhores Destinos, Passageiro de Primeira, Melhores Cartões, Pontos pra Voar, Mestre das Milhas — RSS preferred, scraping as fallback
- Email: Resend (3,000/month) — preferred. Gmail SMTP (500/day) as fallback
- Database: Supabase free tier (PostgreSQL). Errors: Sentry free tier

**Environment variables:**
```
SUPABASE_URL       # Supabase project URL
SUPABASE_KEY       # service key
DATABASE_URL       # PostgreSQL connection string
RESEND_API_KEY     # or GMAIL_APP_PASSWORD as fallback
SENTRY_DSN         # error reporting
SLACK_WEBHOOK_URL  # pipeline error alerts (GitHub Actions secret)
DIGEST_RECIPIENT   # fallback email for pipeline test sends
```

---

## 4. Structure

```
/src
  types.py          # shared contracts: RawSignal, PromotionData, UserPreferencesData
  /pipeline         # main flow: monitors → extractor → dedup → preference_filter → dispatcher
    /monitors       # one file per detection method — all return list[RawSignal]
  /tools            # HTTP utilities used by monitors
  /config           # settings via env vars (pydantic-settings)
  /api              # Pydantic schemas only (reused by Vercel handlers)
    /schemas
  /email/templates  # Jinja2 — day1, confirmation
  /db/migrations    # versioned Alembic migrations
/api                # Vercel Python serverless handlers (one file per route)
  /preferences
  /unsubscribe
/public             # Static registration website (served by Vercel)
/scripts
  run_pipeline.py   # GitHub Actions entry point — python scripts/run_pipeline.py --tier N
/tests
  /unit
  /integration
  /fixtures         # real HTML and RSS for mocks — never fabricate responses
```

---

## 5. Deployment

**Local:** Run directly with Python. Database: production Supabase (via `DATABASE_URL` in `.env`).

No Docker environment — development always points to real Supabase.

**Automation (GitHub Actions):**
- Trigger: 6 cron schedules/day across 2 workflow files
- `pipeline-tier1.yml` — runs at 09h, 12h, 15h, 21h BRT (Tier 1 monitors)
- `pipeline-tier2.yml` — runs at 06h, 18h BRT (Tier 1 + 2 monitors)
- Entry point: `python scripts/run_pipeline.py --tier N`
- Secrets required: `DATABASE_URL`, `RESEND_API_KEY`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `DIGEST_RECIPIENT`, `SENTRY_DSN`, `SLACK_WEBHOOK_URL`
- Each run logs a record in `automation_logs`. Errors trigger a Slack alert.

**Registration site (Vercel):**
- `public/` — static frontend served at `/`
- `api/` — Python serverless handlers at `/api/*`
- Environment variables must be configured in the Vercel project dashboard
- `api/requirements.txt` — lighter dependencies for Vercel functions

**Database (Supabase):**
- Migrations via Alembic: `alembic upgrade head`
- `supabase-keepalive.yml` runs every 5 days to keep the free tier active

---

## 6. Commands

```bash
# Setup (primeira vez)
pip install -r requirements.txt

# Migrations (rodar no Supabase via DATABASE_URL do .env)
alembic upgrade head

# Pipeline manual (local ou CI)
python scripts/run_pipeline.py --tier 1
python scripts/run_pipeline.py --tier 2

# API local dev (Vercel CLI)
vercel dev

# Qualidade — obrigatório antes de declarar qualquer tarefa concluída
ruff check . && ruff format --check . && mypy src/

# Testes
pytest tests/unit/
pytest tests/integration/
```

---

## 7. How to Work Here

- Read the relevant source file before coding — never infer structure from filenames.
- For non-trivial tasks: present a plan and wait for confirmation before implementing.
- Add or update tests for every piece of business logic touched.
- Run the quality check before declaring done.
- **Update this file** whenever architecture or flow changes — in the same task, before declaring done.

---

## 8. Critical Rules

**Secrets:** NEVER commit `.env`. Hardcoded credential detected: stop immediately and report.

**Idempotency:**
- Transfer: `sha256(origin_program + dest_program + bonus_pct + promo_type + ends_at.date())`
- Accumulation: same fingerprint structure via `extractor._fingerprint()`

**Email sequence (day 1 only):**
- Immediate send on first detection of an active promotion.
- `email_log(user_id, promo_id, day_number=1)` is the source of truth — check before any send.
- NEVER send if `promotion.ends_at < now()` or `promotion.ends_at is None`.

**Promotion validity:**
- `ends_at` is REQUIRED — promotions without an end date are discarded by the extractor.
- `starts_at` is optional — if missing, treat as active from publication date.
- "Hoje é o último dia" / "último dia" / "encerra hoje" → `ends_at = article published_date` (end of day).
- The extractor uses `signal.fetched_at` as the article reference date. RSS monitors set `fetched_at = entry.published_parsed`.

**Data integrity:**
- Schema changes via versioned Alembic migration — zero manual `ALTER TABLE`.
- NEVER delete `email_log` records.
- NEVER delete `automation_logs` records.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md to reflect GitHub Actions + Vercel + Supabase architecture"
```

---

## Post-Implementation Checklist

After all tasks are committed:

- [ ] **Add GitHub Actions secrets** in the repository settings:
  - `DATABASE_URL`
  - `RESEND_API_KEY`
  - `GMAIL_USER`
  - `GMAIL_APP_PASSWORD`
  - `DIGEST_RECIPIENT`
  - `SENTRY_DSN`
  - `SLACK_WEBHOOK_URL` = `REDACTED_SLACK_WEBHOOK`

- [ ] **Configure Vercel project:**
  - Connect to the GitHub repo
  - Set environment variables: `DATABASE_URL`, `RESEND_API_KEY`, `GMAIL_APP_PASSWORD`, `DIGEST_RECIPIENT`, `SENTRY_DSN`, `APP_BASE_URL` (your Vercel domain)
  - `public/` is the static output directory

- [ ] **Trigger a manual workflow run** to verify the pipeline works end-to-end:
  ```
  GitHub → Actions → Pipeline — Tier 1 → Run workflow
  ```

- [ ] **Verify Supabase** has the `automation_logs` table and a record appears after the first run.
