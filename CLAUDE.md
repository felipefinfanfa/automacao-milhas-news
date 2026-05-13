# Miles Radar — CLAUDE.md

> Read this file at the start of every session. Keep it updated as the project evolves.

---

## 1. Project

**What it does:** Monitors three types of promotions across Brazilian miles programs (Smiles, Azul, LATAM, Livelo, Esfera) and sends an immediate email alert for every new promotion detected. Target operational cost: zero (except hosting).

**Promotion types:**
- `transfer_bonus` — bonus % when transferring points between programs (e.g. Esfera → Smiles)
- `flight_award` — flights bookable with miles, with IATA route extraction and user route/program filtering
- `other` — accumulation campaigns, card bonuses, etc.

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
- News (RSS): Melhores Destinos, Passageiro de Primeira, Melhores Cartões, Pontos pra Voar, Mestre das Milhas
  - Correct feed URLs in `src/config/settings.py` → `NEWS_RSS_FEEDS`
  - These feeds also contain `flight_award` articles — no separate monitor needed
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
  types.py          # shared contracts: RawSignal, PromotionData, UserPreferencesData, FlightRoute
  /pipeline         # main flow: monitors → extractor → dedup → preference_filter → dispatcher
    /monitors       # one file per detection method — all return list[RawSignal]
  /tools            # HTTP utilities used by monitors
  /config
    settings.py     # env vars, NEWS_RSS_FEEDS, LOYALTY_PROGRAMS, VALID_TRANSFER_PAIRS
    airports.py     # CITY_TO_IATA (city→IATA mapping) + AIRPORTS_LIST (frontend autocomplete)
  /api              # Pydantic schemas only (reused by Vercel handlers)
    /schemas
      preferences.py  # UserPreferencesIn/Out, TransferPairIn, FlightRouteIn
  /email/templates  # Jinja2 — day1.html, confirmation.html
  /db
    models.py       # SQLAlchemy models — Promotion, UserPreferences, EmailLog, etc.
    /migrations     # versioned Alembic migrations (current head: 009)
/api                # Vercel Python serverless handlers (one file per route)
  /preferences
  /unsubscribe
/public             # Static registration website (served by Vercel)
  /js/app.js        # all frontend JS including flight preferences logic
/scripts
  run_pipeline.py    # GitHub Actions entry point — python scripts/run_pipeline.py --tier N
  run_now.py         # scan manual + envio imediato para DIGEST_RECIPIENT
  send_test_email.py # envia confirmation e day1 com dados mock (sem banco, sem dedup)
  backfill_promos.py # reprocessa snapshots históricos — sempre usar --dry-run primeiro
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

**Idempotency — fingerprint by promo_type:**
- `transfer_bonus`: `sha256([origin_program, dest_program, bonus_pct, "transfer_bonus", ends_at.date()])`
- `flight_award` with route resolved: `sha256([origin_iata, destination_iata, "flight_award", ends_at.date()])`
- `flight_award` without route: `sha256([source_url, "flight_award", ends_at.date()])` — prevents same-day collision
- `other`/accumulation: same structure as transfer_bonus via `extractor._fingerprint()`

**Email sequence (day 1 only):**
- Immediate send on first detection of an active promotion.
- `email_log(user_id, promo_id, day_number=1)` is the source of truth — check before any send.
- NEVER send if `promotion.ends_at < now()` or `promotion.ends_at is None`.

**Promotion validity:**
- `ends_at` is REQUIRED for ALL promo types including `flight_award` — articles without an end date are discarded.
- `starts_at` is optional — if missing, treat as active from publication date.
- "Hoje é o último dia" / "último dia" / "encerra hoje" → `ends_at = article published_date` (end of day).
- The extractor uses `signal.fetched_at` as the article reference date. RSS monitors set `fetched_at = entry.published_parsed`.

**flight_award preference matching:**
- Users configure `flight_routes: list[FlightRoute]` (each has optional `origin_iata`/`destination_iata`) and `flight_programs: list[str]`.
- At least one of origin_iata or destination_iata must be set per route (validated in frontend).
- Match logic: program filter (AND) → route OR-logic. `None` on a route field = wildcard.
- RSS articles have `source_program="unknown"` — the loyalty program is detected from text and stored in `origin_program`. The program filter uses `promo.origin_program or promo.source_program`. Articles where no known program is detected pass the filter (don't drop silently).
- Route extraction uses `src/config/airports.py:CITY_TO_IATA` to map city names → IATA codes.

**Data integrity:**
- Schema changes via versioned Alembic migration — zero manual `ALTER TABLE`.
- NEVER delete `email_log` records.
- NEVER delete `automation_logs` records.
