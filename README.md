# Radar de Milhas

Monitoramento automático de promoções de milhas dos principais programas brasileiros. Detecta novas promoções em até 1 hora e envia alertas por e-mail personalizados conforme as preferências de cada usuário.

**Programas monitorados:** Smiles · Azul TudoAzul · LATAM Pass · Livelo · Esfera

**Tipos de promoção detectados:**
- **Transferência com bônus** — bônus % ao transferir pontos entre programas (ex: Esfera → Smiles 100%)
- **Passagens emitidas com milhas** — alertas de voos, filtráveis por rota IATA e programa
- **Outras** — acúmulo de pontos, bônus de cartões, etc.

---

## Como funciona

O pipeline roda 6× por dia via GitHub Actions (06h, 09h, 12h, 15h, 18h, 21h BRT). Quando uma promoção nova ativa é detectada, e-mail consolidado é enviado para os usuários cujas preferências batem com ela.

```
[GitHub Actions Cron]
        ↓
[news_monitor]        # RSS dos 5 blogs + fetch HTML completo (filtra últimos 48h)
        ↓
[extractor]           # texto → PromotionData (date-context-aware)
        ↓
[dedup]               # fingerprint mensal + verificação semântica
        ↓
[preference_filter]   # filtra por programa / par de transferência / rota IATA
        ↓
[dispatcher → Resend] # consolidado, sem duplicatas
```

**Fontes RSS:** Melhores Destinos, Passageiro de Primeira, Pontos pra Voar, Mestre das Milhas, Melhores Cartões.

3 dos 5 feeds só retornam summary curto — o monitor busca o HTML completo do artigo usando seletores site-específicos para extrair contexto.

---

## Stack

- **Python 3.12** — pipeline determinístico, sem framework web
- **Scraping** — `httpx` · `BeautifulSoup4` · `feedparser`
- **Banco** — Supabase (PostgreSQL) via `SQLAlchemy 2` + `Alembic`
- **E-mail** — Resend (único provedor) · templates `Jinja2`
- **Validação** — `Pydantic v2`
- **Frontend** — site estático em `public/` servido pelo Vercel
- **API** — handlers Python serverless em `api/` (Vercel Functions)
- **CI/CD** — GitHub Actions (cron + deploy)

---

## Estrutura

```
src/
├── pipeline/
│   ├── monitors/news_monitor.py   # único monitor — RSS + fetch HTML completo
│   ├── extractor.py               # extração + classificação + fingerprint
│   ├── dedup.py                   # 2 camadas: fingerprint + semântico
│   ├── preference_filter.py
│   └── dispatcher.py              # envio via Resend
├── db/
│   ├── models.py                  # ORM
│   └── migrations/                # Alembic, head: 010
├── api/schemas/preferences.py     # schemas reutilizados pelos handlers Vercel
├── config/settings.py             # env vars + NEWS_RSS_FEEDS + programas válidos
├── config/airports.py             # CITY_TO_IATA
├── tools/http_client.py           # httpx, delay 2-5s por domínio
├── email/templates/               # day1.html, confirmation.html
└── types.py                       # RawSignal, PromotionData, FlightRoute, etc.

api/                               # handlers Vercel (cadastro de usuários)
public/                            # site estático
scripts/run_pipeline.py            # entry point GitHub Actions
.github/workflows/pipeline.yml     # cron 6×/dia
```

---

## Setup local

```bash
pip install -r requirements.txt
cp .env.example .env               # preencher DATABASE_URL e RESEND_API_KEY
alembic upgrade head
python scripts/run_pipeline.py
```

**API local (Vercel CLI):** `vercel dev`

---

## Variáveis de ambiente

| Variável | Descrição |
|----------|-----------|
| `DATABASE_URL` | Connection string PostgreSQL/Supabase (service role) |
| `RESEND_API_KEY` | Chave Resend |
| `DIGEST_RECIPIENT` | E-mail para testes manuais |
| `SENTRY_DSN` | DSN Sentry (opcional) |
| `SLACK_WEBHOOK_URL` | Alertas de erro (opcional) |
| `APP_ENV` | `production` ou `development` |

---

## Qualidade

```bash
ruff check . && ruff format --check . && mypy src/
pytest tests/unit/
```

---

## Deploy

**Pipeline (GitHub Actions):**
- `.github/workflows/pipeline.yml` — cron 6×/dia
- `.github/workflows/supabase-keepalive.yml` — a cada 5 dias

**Frontend + API (Vercel):**
- `public/` servido em `milhas.felipefinfanfa.com.br`
- `api/` exposto em `/api/*` como Vercel Functions
