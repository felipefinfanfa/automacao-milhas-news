# Miles Radar — CLAUDE.md

> Read this file at the start of every session. Keep it updated as the project evolves.

---

## 1. Project

**What it does:** Monitors transfer and accumulation promotions across Brazilian miles programs (Smiles, Azul, LATAM, Livelo, Esfera) and sends an immediate email alert for every new promotion detected, for up to 3 consecutive days. Target operational cost: zero (except hosting).

**Trigger:** Cron at 6 times/day (06h, 09h, 12h, 15h, 18h, 21h BRT). Email sent whenever a new promotion is detected — no routine digest.

**Output:** Consolidated email per user with active promotions matching their preferences.

**Criticality:** Medium — up to 1h delay is acceptable.

---

## 2. Automation Mode

### MODE A — Deterministic Pipeline

**Flow:**
```
[Cron] → [Monitors] → [Extractor] → [Dedup] → [Preference Filter] → [Email Dispatcher]
```

Monitors run in parallel across distinct domains. Each step is a deterministic function. No agent, no memory, no complex state.

---

## 3. Stack

**Runtime:** Python 3.12

**Dependencies:**
- `playwright` + `playwright-stealth` — JS-heavy scraping and visual diff
- `cloudscraper` — Cloudflare bypass
- `httpx` — async HTTP for RSS, sitemaps and public APIs
- `beautifulsoup4` + `lxml` + `feedparser` — HTML and RSS parsing
- `imagehash` — visual diff via perceptual hash
- `pydantic v2` — schema validation
- `apscheduler` — scan and email scheduling
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
  /api              # FastAPI — user preferences
  /email/templates  # Jinja2 — day1, day2, day3, confirmation
  /scheduler        # APScheduler entry point; /jobs with tiers 1–3
  /db/migrations    # versioned Alembic migrations
/tests
  /unit
  /integration
  /fixtures         # real HTML and RSS for mocks — never fabricate responses
/scripts            # manual entrypoints — all support --dry-run
```

---

## 5. Deployment

**Local:** Run directly with Python. Database: production Supabase (via `DATABASE_URL` in `.env`).

No local Docker environment — development always points to real Supabase.

**Production (single-node Docker Swarm on Hostinger VPS):**

Push to `master` triggers a two-job GitHub Actions workflow:
1. **Build** — builds Docker image (`target: runtime`), pushes to `ghcr.io/felipefinfanfa/radar-de-milhas:latest` and `:<sha>`.
2. **Deploy** — SSHes into VPS, runs `docker stack deploy -c docker-stack.yml radar-de-milhas`.

Key files:
- `Dockerfile` — multi-stage (base → deps → runtime). Playwright/Chromium in `deps`.
- `docker-stack.yml` — Swarm stack: `scheduler` (1 replica, 1g) + `api` (1 replica, 512m). Traefik labels under `deploy.labels`.
- `.github/workflows/deploy.yml` — CI/CD pipeline.

Network: `felipefinfanfanet` is an overlay+attachable network created once on the VPS. Traefik connects to it as a standalone container.

Secrets on VPS: `/opt/miles-radar/.env` — never committed.

**Useful VPS commands:**
```bash
docker stack services radar-de-milhas
docker stack ps radar-de-milhas --no-trunc
docker service logs radar-de-milhas_api --tail 100 --follow
docker service logs radar-de-milhas_scheduler --tail 100 --follow

# Force redeploy without a push
docker stack deploy --with-registry-auth -c /opt/miles-radar/docker-stack.yml radar-de-milhas

# Rollback to a specific build
docker service update --image ghcr.io/felipefinfanfa/radar-de-milhas:<SHA> radar-de-milhas_api
docker service update --image ghcr.io/felipefinfanfa/radar-de-milhas:<SHA> radar-de-milhas_scheduler

# Remove stack
docker stack rm radar-de-milhas
```

---

## 6. Commands

```bash
# Setup (primeira vez)
pip install -r requirements.txt && playwright install chromium

# Migrations (rodar no Supabase via DATABASE_URL do .env)
alembic upgrade head

# Scan imediato (sem scheduling)
python scripts/run_now.py            # Tier 1 — fastest
python scripts/run_now.py --tier 2   # Tier 1 + Tier 2

# Scheduler
python -m src.scheduler              # 6 crons/day em loop
python -m src.scheduler --dry-run    # 1 ciclo Tier 3 completo, sem emails

# API de preferências
uvicorn src.api.main:app --reload

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
- Transfer: `sha256(source_program + dest_program + bonus_pct + start_date)`
- Accumulation: `sha256(program + multiplier + trigger + start_date)`

**Email sequence:**
- Day 1: immediate send on first detection.
- Day 2 and 3: exactly 24h and 48h after Day 1 via APScheduler one-shot jobs.
- `email_log(user_id, promo_id, day_number, sent_at)` is the source of truth — check before any send.
- NEVER send if `promotion.valid_until < now()`. Extending end_date does not restart the sequence.

**Data integrity:**
- Schema changes via versioned Alembic migration — zero manual `ALTER TABLE`.
- NEVER delete `email_log` records.
- `backfill_promos.py`: NEVER run without `--dry-run` first.
