# Radar de Milhas — Deployment Restructure Design

**Date:** 2026-05-08  
**Status:** Approved

---

## Overview

Migrate the system from a single-node Docker Swarm on a Hostinger VPS to a fully serverless architecture:

- **Automation (pipeline):** GitHub Actions — 6 cron runs/day across 2 workflow files
- **Registration site:** Vercel — static frontend + Python serverless API functions
- **Database:** Supabase (unchanged)
- **Observability:** New `automation_logs` table in Supabase + Slack alerts on error

Remove all Docker infrastructure, APScheduler, Playwright/visual diff, and the 3-day email sequence (day 1 only retained).

---

## 1. GitHub Actions Automation

### Workflow Files

Two separate workflow files in `.github/workflows/`:

| File | Cron (UTC) | BRT | Tier |
|------|------------|-----|------|
| `pipeline-tier1.yml` | 12h, 15h, 18h, 00h | 09h, 12h, 15h, 21h | 1 |
| `pipeline-tier2.yml` | 09h, 21h | 06h, 18h | 2 |

Both support `workflow_dispatch` for manual runs. Both call:
```bash
python scripts/run_pipeline.py --tier N
```

### Pipeline Entry Point: `scripts/run_pipeline.py`

Replaces `src/scheduler/` entirely. Responsibilities:
1. Accept `--tier [1|2]` argument
2. Run the appropriate monitors in parallel
3. Extract → dedup → preference filter → dispatch emails
4. Write a record to `automation_logs` on every run (success or error)
5. On unhandled exception: write error to `automation_logs`, post Slack alert, exit with code 1

### Slack Error Alerts

Webhook URL stored as GitHub Actions secret `SLACK_WEBHOOK_URL` (never hardcoded).

Alert format:
```
❌ *Radar de Milhas — Pipeline Error*
Tier: 2 | Run: <link to GH Actions run>
Error: <exception type>: <message>
```

Sent via `httpx.post()` to the webhook URL on any unhandled exception.

### GitHub Actions Secrets Required

| Secret | Purpose |
|--------|---------|
| `DATABASE_URL` | Supabase PostgreSQL connection |
| `RESEND_API_KEY` | Primary email sending |
| `GMAIL_APP_PASSWORD` | Email fallback |
| `SENTRY_DSN` | Error tracking |
| `SLACK_WEBHOOK_URL` | Pipeline error alerts |

### Monitor Tiers (revised)

| Tier | Monitors |
|------|---------|
| 1 | `direct_scraper`, `hash_diff`, `rss_monitor`, `google_news` |
| 2 | Tier 1 + `sitemap_monitor`, `robots_monitor`, `news_scraper` |

Tier 3 (visual diff / Playwright) is removed entirely.

---

## 2. Vercel Registration Site

### Directory Layout

```
public/                        ← static frontend (moved from src/api/static/)
  index.html
  assets/
  css/
  js/

api/                           ← Vercel Python serverless functions
  preferences/
    register.py                → POST  /api/preferences/register
    slots.py                   → GET   /api/preferences/slots
    programs/
      list.py                  → GET   /api/preferences/programs/list
    [user_id].py               → GET + PUT /api/preferences/{user_id}
  unsubscribe/
    [token].py                 → GET   /api/unsubscribe/{token}

vercel.json                    ← routing config
requirements-vercel.txt        ← lightweight deps (no playwright, no apscheduler)
```

### Handler Pattern

Each file in `api/` uses Vercel's Python serverless pattern:
```python
from http.server import BaseHTTPRequestHandler

class handler(BaseHTTPRequestHandler):
    def do_GET(self): ...
    def do_POST(self): ...
```

Handlers reuse:
- `src/db/` — database models and session factory
- `src/api/schemas/preferences.py` — Pydantic models (RegisterIn, RegisterOut, UserPreferencesIn, UserPreferencesOut) kept as-is
- `src/pipeline/dispatcher.py` — confirmation email dispatch

`src/api/routes/preferences.py` is **removed** (it is FastAPI-specific: uses `APIRouter`, `Depends`). Its logic is rewritten inline in each Vercel handler.
`src/api/main.py` is **removed**. No FastAPI, no uvicorn.

### `vercel.json`

- Rewrites `/api/*` to the serverless functions
- Serves everything else from `public/`

---

## 3. Database — `automation_logs` Table

New Alembic migration `008_add_automation_logs.py`:

```sql
CREATE TABLE automation_logs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    workflow         TEXT NOT NULL,        -- 'pipeline-tier1' | 'pipeline-tier2'
    tier             INTEGER NOT NULL,
    status           TEXT NOT NULL,        -- 'success' | 'error' | 'partial'
    signals_found    INTEGER DEFAULT 0,
    promos_new       INTEGER DEFAULT 0,
    emails_sent      INTEGER DEFAULT 0,
    error_message    TEXT,
    error_traceback  TEXT,
    duration_seconds FLOAT,
    gh_run_id        TEXT                  -- GitHub Actions run ID for traceability
);
```

- No foreign keys — write-only audit log
- Records are never deleted
- Queryable from Supabase dashboard to diagnose failures

### Existing Schema — Promotion Validity

- `promotions.ends_at`: if `NULL` after extraction → promotion is **discarded**, never saved to DB
- `promotions.starts_at`: optional; if `NULL`, treated as active from publication date
- `preference_filter.py` active check tightened to: `ends_at is not None and ends_at > now()`

---

## 4. Removals

### Infrastructure
- `Dockerfile`
- `docker-stack.yml`
- `.dockerignore`
- `.github/workflows/deploy.yml`

### Pipeline
- `src/scheduler/` (entire directory)
- `src/pipeline/sequence.py`
- `src/pipeline/monitors/visual_diff.py`

### API (replaced by Vercel functions)
- `src/api/main.py`
- `src/api/routes/preferences.py` (FastAPI-specific; logic rewritten in Vercel handlers)
- `src/api/static/` (content moved to `public/`)

### Dependencies (removed from `requirements.txt`)
- `apscheduler`
- `playwright`
- `playwright-stealth`
- `imagehash`
- `pillow`
- `uvicorn`
- `python-multipart`
- `itsdangerous`

### Kept
- `.github/workflows/supabase-keepalive.yml` — still needed for Supabase free tier

---

## 5. Scraping Review & Promotion Validity

### Files to Audit and Fix

**`src/pipeline/monitors/direct_scraper.py`**  
Audit CSS selectors and URL targets for each program (Smiles, Azul, LATAM, Livelo, Esfera). Fix any broken selectors or outdated URLs.

**`src/pipeline/monitors/news_scraper.py`** and **`rss_monitor.py`**  
Verify RSS feed URLs and fallback scraping selectors for all 5 news sources.

**`src/pipeline/extractor.py`** — critical changes:

1. `ends_at` is now **required**: if no end date is parsed → return `[]` (discard the signal)

2. `RawSignal` gets a `published_at: Optional[datetime]` field:
   - RSS: populated from feedparser's `entry.published_parsed`
   - Direct scrape: parsed from article HTML if available; `None` otherwise

3. "Last day" detection rules — `ends_at = published_at` (article publication date, end of day 23:59:59):
   - `"hoje é o último dia"`
   - `"último dia"`
   - `"encerra hoje"`
   - `"válido até hoje"`
   - `"termina hoje"`
   - Similar Portuguese phrases

4. Duration rule: `"válido por X dias"` → `ends_at = starts_at + X days`

5. Fingerprint unchanged: `SHA256(origin + dest + bonus_pct + promo_type + ends_at.date())`

**`src/pipeline/dispatcher.py`**  
Remove all calls to `schedule_followup_days()` and any APScheduler imports. The `dispatch_upcoming()` function (for future promos) is also removed — the simplified day-1-only flow only uses `dispatch_day1()`. Remove the `scheduler` parameter from all function signatures.

**`src/pipeline/preference_filter.py`**  
Tighten active promo check:
```python
# Before
ends_at > now()
# After
ends_at is not None and ends_at > now()
```

---

## 6. CLAUDE.md Updates

- **Deployment section**: replace all Docker/VPS content with GitHub Actions + Vercel + Supabase description
- **Commands section**: remove Docker commands; add `python scripts/run_pipeline.py --tier N` and `vercel dev`
- **Structure section**: update paths (`public/` instead of `src/api/static/`; `api/` for Vercel functions; remove `src/scheduler/` and deprecated pipeline files)
- **Critical rules**: simplify email sequence to day 1 only; remove APScheduler follow-up rule
- **Stack section**: remove APScheduler, Playwright, imagehash, pillow; add Vercel deployment note

---

## Email Sequence (Simplified)

Day 1 only. On every pipeline run:
1. Find all active promotions (`ends_at > now()`, has `bonus_percent`, `ends_at is not None`)
2. Load all user preferences
3. For each user: filter promotions matching their pairs/programs
4. For each matching promo: check `email_log` — if `(user_id, promo_id, day_number=1)` already exists, skip
5. If not sent: send email, record in `email_log`

`email_log` table and `UNIQUE(user_id, promo_id, day_number)` constraint remain unchanged.
