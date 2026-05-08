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
