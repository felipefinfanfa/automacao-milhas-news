# Radar de Milhas

Monitoramento automático de promoções de transferência e acúmulo de milhas nos principais programas brasileiros. Detecta novas promoções em até 1 hora e envia alertas por e-mail personalizados de acordo com as preferências de cada usuário.

**Programas monitorados:** Smiles · Azul TudoAzul · LATAM Pass · Livelo · Esfera

---

## Como funciona

O sistema roda 6 varreduras por dia (06h, 09h, 12h, 15h, 18h, 21h BRT) usando três camadas de monitoramento:

| Tier | Quando | Monitores |
|------|--------|-----------|
| 1 | Todos os 6 scans | Landing pages, hash diff, RSS de notícias, Google News |
| 2 | 09h e 18h | Sitemap, robots.txt, scraping direto de notícias |
| 3 | 06h | URL fuzzing, visual diff (Playwright), CT logs, DNS |

Ao detectar uma nova promoção, o sistema envia até 3 e-mails por usuário (dia 1, 24h e 48h depois) — apenas se a promoção ainda estiver ativa e bater com as preferências cadastradas.

---

## Stack

- **Python 3.12** — FastAPI · APScheduler · SQLAlchemy 2 · Alembic · Pydantic v2
- **Scraping** — Playwright + stealth · cloudscraper · httpx · BeautifulSoup4
- **Banco** — Supabase (PostgreSQL)
- **E-mail** — Resend (primário) · Gmail SMTP (fallback)
- **Deploy** — Docker · Traefik · VPS Hostinger · GitHub Actions

---

## Estrutura

```
src/
├── monitors/          # 1 arquivo por método de detecção
├── processor/         # extração, dedup e filtro por preferências
├── email/             # dispatcher, sequência de 3 dias e templates Jinja2
├── scheduler/jobs/    # tier1.py · tier2.py · tier3.py
├── api/               # FastAPI — cadastro e preferências do usuário
├── db/                # models SQLAlchemy + migrations Alembic
└── config/            # settings via pydantic-settings
```

---

## Setup local

**Pré-requisitos:** Python 3.12, Docker

```bash
# Dependências
pip install -r requirements.txt
playwright install chromium

# Banco
cp .env.example .env   # preencher DATABASE_URL e demais variáveis
alembic upgrade head

# Rodar (sem Traefik)
DOCKER_BUILDKIT=0 docker-compose -f docker-compose.yml -f docker-compose.local.yml up

# Testar 1 ciclo completo sem enviar e-mails
python -m src.scheduler.jobs --dry-run

# API em modo desenvolvimento
uvicorn src.api.main:app --reload
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
| `DIGEST_RECIPIENT` | E-mail do destinatário do digest |
| `SENTRY_DSN` | DSN Sentry (opcional) |
| `APP_ENV` | `production` ou `development` |

Veja `.env.example` para o template completo.

---

## Qualidade

```bash
ruff check . && ruff format --check . && mypy src
pytest tests/unit
pytest tests/integration   # requer .env com Supabase de teste
```

Cobertura mínima: 85% em `src/processor/` e `src/email/`.

---

## Deploy

Push para `master` dispara deploy automático via GitHub Actions:

1. SSH na VPS Hostinger
2. `git pull origin master`
3. `docker compose up -d --build`

A API fica exposta em `milhas.felipefinfanfa.com.br` via Traefik com TLS automático.
