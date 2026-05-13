# Radar de Milhas

Monitoramento automático de promoções de transferência e acúmulo de milhas nos principais programas brasileiros. Detecta novas promoções em até 1 hora e envia alertas por e-mail personalizados de acordo com as preferências de cada usuário.

**Programas monitorados:** Smiles · Azul TudoAzul · LATAM Pass · Livelo · Esfera

---

## Como funciona

O pipeline roda 6 vezes por dia via GitHub Actions (06h, 09h, 12h, 15h, 18h, 21h BRT). Quando uma nova promoção é detectada, um e-mail é enviado imediatamente para todos os usuários cujas preferências batem com ela.

```
[GitHub Actions Cron]
        ↓
   [Monitors]          # coleta sinais das fontes
        ↓
   [Extractor]         # interpreta e valida cada sinal
        ↓
   [Dedup]             # descarta o que já foi visto
        ↓
[Preference Filter]    # filtra por programa/par de cada usuário
        ↓
[Email Dispatcher]     # envia via Resend ou Gmail SMTP
```

### Tiers de monitoramento

| Tier | Scans | Monitores |
|------|-------|-----------|
| 1 | 09h, 12h, 15h, 21h | Landing pages dos programas, hash diff, RSS de notícias, Google News |
| 2 | 06h, 18h | Tier 1 + sitemap, robots.txt, scraping direto de notícias |

---

## Stack

- **Python 3.12** — pipeline determinístico, sem framework web
- **Scraping** — `cloudscraper` (bypass Cloudflare) · `httpx` · `BeautifulSoup4` · `feedparser`
- **Banco** — Supabase (PostgreSQL) via `SQLAlchemy 2` + `Alembic`
- **E-mail** — Resend (primário) · Gmail SMTP (fallback) · templates `Jinja2`
- **Validação** — `Pydantic v2`
- **Frontend** — site estático em `public/` servido pelo Vercel
- **API** — handlers Python serverless em `api/` (Vercel Functions)
- **CI/CD** — GitHub Actions (cron + deploy)

---

## Estrutura

```
src/
├── pipeline/
│   ├── monitors/      # um arquivo por método de detecção → list[RawSignal]
│   ├── extractor.py   # RawSignal → PromotionData
│   ├── dedup.py       # fingerprint SHA-256, persiste no banco
│   ├── preference_filter.py
│   └── dispatcher.py  # Resend → Gmail SMTP fallback
├── db/
│   ├── models.py
│   └── migrations/    # versionadas via Alembic
├── api/schemas/       # schemas Pydantic reutilizados pelos handlers Vercel
├── config/settings.py
├── tools/             # HTTP client, user-agent rotation
├── email/templates/   # confirmation.html · day1.html (Jinja2)
└── types.py           # contratos: RawSignal, PromotionData, UserPreferencesData

api/                   # handlers Python serverless (Vercel)
├── preferences/
│   ├── register.py
│   ├── slots.py
│   └── [user_id].py
└── unsubscribe/
    └── [token].py

public/                # site de cadastro (HTML/CSS/JS estático)
scripts/
├── run_pipeline.py    # entry point do GitHub Actions
├── run_now.py         # scan manual + envio imediato
├── send_test_email.py # envia templates com dados mock (sem tocar no banco)
└── backfill_promos.py # reprocessa snapshots históricos (--dry-run obrigatório)
```

---

## Setup local

**Pré-requisitos:** Python 3.12

```bash
# Dependências
pip install -r requirements.txt

# Configurar variáveis
cp .env.example .env   # preencher DATABASE_URL, credenciais de e-mail etc.

# Rodar migrations
alembic upgrade head

# Executar pipeline manualmente
python scripts/run_pipeline.py --tier 1
python scripts/run_pipeline.py --tier 2

# Testar envio de e-mail (sem banco, dados mock)
python scripts/send_test_email.py
python scripts/send_test_email.py --template confirmation
python scripts/send_test_email.py --template day1

# API local (Vercel CLI)
vercel dev
```

---

## Variáveis de ambiente

| Variável | Descrição |
|----------|-----------|
| `DATABASE_URL` | Connection string PostgreSQL (Supabase) |
| `SUPABASE_URL` | URL do projeto Supabase |
| `SUPABASE_KEY` | Service role key |
| `RESEND_API_KEY` | Chave Resend (e-mail primário) |
| `GMAIL_USER` / `GMAIL_APP_PASSWORD` | Fallback SMTP |
| `DIGEST_RECIPIENT` | E-mail para testes manuais |
| `SENTRY_DSN` | DSN Sentry (opcional) |
| `APP_ENV` | `production` ou `development` |

Veja `.env.example` para o template completo.

---

## Qualidade

```bash
ruff check . && ruff format --check . && mypy src/
pytest tests/unit/
pytest tests/integration/   # requer .env com Supabase configurado
```

---

## Deploy

**Pipeline (GitHub Actions):**
- `pipeline-tier1.yml` — 09h, 12h, 15h, 21h BRT
- `pipeline-tier2.yml` — 06h, 18h BRT
- `supabase-keepalive.yml` — a cada 5 dias (mantém o free tier ativo)

**Frontend + API (Vercel):**
- `public/` servido em `milhas.felipefinfanfa.com.br`
- `api/` exposto em `/api/*` como Vercel Functions
