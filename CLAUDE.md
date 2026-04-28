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

**Local:** Rodar diretamente com Python. Banco de dados: Supabase de produção (via `DATABASE_URL` no `.env`).

**Produção (VPS):** Push para `master` no GitHub → VPS puxa automaticamente e sobe via Docker.
- `Dockerfile` — imagem de produção (scheduler).
- `docker-compose.yml` — orquestra scheduler + api com Traefik/HTTPS em `milhas.felipefinfanfa.com.br`.

Não existe ambiente Docker local — desenvolvimento sempre aponta para o Supabase real.

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
