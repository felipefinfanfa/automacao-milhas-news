# Miles Radar — CLAUDE.md

> Read this file at the start of every session. Keep it updated as the project evolves.

---

## 1. Project

Monitora promoções de programas brasileiros de milhas (Smiles, Azul, LATAM, Livelo, Esfera) raspando 5 blogs de notícia, deduplicando e enviando e-mail via Resend. Custo operacional: zero (exceto hospedagem).

**Tipos de promoção:**
- `transfer_bonus` — bônus % em transferências entre programas
- `flight_award` — passagens com milhas (com IATA e filtro de rota/programa)
- `other` — acúmulo, bônus de cartão, etc.

**Trigger:** Cron GitHub Actions 6x/dia (06h, 09h, 12h, 15h, 18h, 21h BRT). E-mail consolidado por usuário, enviado quando há promo nova ativa.

---

## 2. Pipeline

```
[GitHub Actions Cron] → [news_monitor] → [extractor] → [dedup] → [preference_filter] → [dispatcher → Resend]
```

Cada etapa é função determinística. Sem agente, sem memória, sem estado complexo.

---

## 3. Stack

**Runtime:** Python 3.12

**Dependências runtime:**
- `httpx` — HTTP
- `beautifulsoup4` + `lxml` + `feedparser` — parsing
- `pydantic v2` — schemas
- `sqlalchemy 2` + `alembic` — ORM/migrations
- `jinja2` — templates
- `resend` — e-mail (único provedor)
- `sentry-sdk` — observabilidade

**Integrações:**
- 5 blogs RSS: Melhores Destinos, Passageiro de Primeira, Pontos pra Voar, Mestre das Milhas, Melhores Cartões
- Resend (3k e-mails/mês)
- Supabase free tier (PostgreSQL)
- Sentry free tier

**Variáveis de ambiente:**
```
DATABASE_URL       # PostgreSQL (service role — bypassa RLS)
RESEND_API_KEY
EMAIL_FROM         # default: "Radar de Milhas <noreply@example.com>"
DIGEST_RECIPIENT   # fallback para testes
APP_BASE_URL       # default: "https://localhost:3000" — usado em links de e-mail
SENTRY_DSN
SLACK_WEBHOOK_URL  # alertas de erro do pipeline
```

---

## 4. Estrutura

```
/src
  types.py                      # RawSignal, PromotionData, UserPreferencesData, FlightRoute
                                # TransferPair, PromoType, SourceType = "rss"
  /pipeline
    /monitors
      news_monitor.py           # único monitor — RSS + fetch HTML completo dos artigos
    extractor.py                # RawSignal → PromotionData (date-context-aware, usa site_rules)
    site_rules.py               # SiteRule dataclass + SITE_RULES por fonte (5 sites)
    dedup.py                    # fingerprint SHA-256 + verificação semântica
    preference_filter.py        # matching usuário × promoção
    dispatcher.py               # envio via Resend (day1 + confirmation)
  /tools
    http_client.py              # httpx-only, delay 2-5s por domínio
    user_agents.py
  /config
    settings.py                 # NEWS_RSS_FEEDS, LOYALTY_PROGRAMS, VALID_TRANSFER_PAIRS
    airports.py                 # CITY_TO_IATA + AIRPORTS_LIST
  /api/schemas
    preferences.py              # validators usados pelos handlers Vercel
  /email/templates
    day1.html, confirmation.html
  /db
    models.py                   # Promotion, UserPreferences, EmailLog, MonitorState, AutomationLog
    /migrations                 # Alembic, head: 012
/api                            # Vercel Python serverless handlers (cadastro)
  /preferences
  /unsubscribe
/public                         # Site estático (Vercel)
/scripts
  run_pipeline.py               # entry point GitHub Actions
/tests/unit                     # 78 testes
  test_extractor.py
  test_extractor_flight_award.py
  test_extractor_site_rules.py
  test_dedup.py
  test_preference_filter.py
  test_preference_filter_flight.py
  test_airports.py
/tests/fixtures
  rss_melhores_destinos.xml
```

---

## 5. Deploy

**Local:** Python direto. Banco: Supabase de produção (via `DATABASE_URL` no `.env`).

**Automação (GitHub Actions):**
- Workflow: `.github/workflows/pipeline.yml`
- 6 schedules/dia
- Entry point: `python scripts/run_pipeline.py`
- Secrets: `DATABASE_URL`, `RESEND_API_KEY`, `DIGEST_RECIPIENT`, `SENTRY_DSN`, `SLACK_WEBHOOK_URL`

**Site de cadastro (Vercel):**
- `public/` → frontend em `/`
- `api/` → handlers Python em `/api/*`

**Supabase:**
- Migrations: `alembic upgrade head`
- RLS habilitada em todas as tabelas (migration 010). Service role bypassa RLS.
- `supabase-keepalive.yml` mantém free tier ativo.

---

## 6. Comandos

```bash
pip install -r requirements.txt
alembic upgrade head
python scripts/run_pipeline.py

# Quality gate
ruff check . && ruff format --check . && mypy src/
pytest tests/unit/
```

---

## 7. Regras Críticas

**Secrets:** NUNCA commit `.env`.

**news_monitor.py — coleta:**
- Lê os 5 feeds RSS, filtra artigos das últimas 48h e título com keywords promocionais.
- Se o RSS retorna < 1500 chars, busca o HTML completo do artigo.
- Seletores site-específicos (`_SITE_SELECTORS`): primeira match vence (não a mais longa) — evita capturar sidebars.
- Strip de `script/style/iframe/nav/header/footer/aside` antes de extrair texto.

**extractor.py — classificação:**
- `_classify_promo_type` aplica regras na ordem: confirm_flight_award → confirm_transfer_bonus → confirm_accumulation → reject rules → generic transfer_bonus → generic flight_award → other.
- Regras por site ficam em `site_rules.py` (SITE_RULES dict). Sites sem regra usam apenas a lógica genérica.
- `_GLOBAL_TRANSFER_EXCLUDE_RE` bloqueia transfer_bonus em textos de compra direta de milhas ou acúmulo por real gasto — aplicado antes das regras de site.

**extractor.py — datas:**
- `_extract_date_range` é **context-aware**: datas com "válido até", "termina", "encerra", "expira", "prazo", "até" → end_candidates. Demais → start_candidates.
- ends_at = última data de fim no futuro (prevê confusão com datas de sidebars/relacionados).
- Range "X a Y" sem keyword: assume min/max.
- Fallback: linguagem natural ("hoje é o último dia").
- `ends_at` é OBRIGATÓRIO — artigos sem data de fim são descartados.

**Idempotency — fingerprint (granularidade mensal):**
- `transfer_bonus`: `sha256([origin, dest, bonus_pct_int, "transfer_bonus", YYYY-MM])`
- `flight_award` com rota: `sha256([origin_iata, dest_iata, "flight_award", YYYY-MM])`
- `flight_award` sem rota: `sha256([source_url, "flight_award", YYYY-MM])`
- `other`: `sha256([origin, "", bonus_pct_int or "", "other", YYYY-MM])`

**Dedup (3 camadas):**
1. Fingerprint SHA-256 exato
2. **Semântico em dedup.py:** mesmo (promo_type, origin, dest) com bonus ±5%; flight_award com dest_iata igual + origin compatível (ou NULL)
3. **Semântico no dispatch:** se usuário já recebeu promo equivalente, skip

**E-mail:**
- Único provedor: Resend.
- `email_log(user_id, promo_id, day_number=1)` é fonte da verdade.
- NUNCA enviar se `ends_at < now()` ou `ends_at is None`.

**flight_award preference matching:**
- Filtro programa (AND) → filtro rota (OR-logic, `None` = wildcard).
- Artigos sem programa identificado passam o filtro (não dropam silenciosamente).

**Segurança:**
- RLS habilitada em todas as tabelas (migration 010).
- Service role usado pelo pipeline e API Vercel bypassa RLS.
- Anon PostgREST bloqueado por policies `deny_all_*`.

**Data integrity:**
- Mudanças de schema só via Alembic migration versionada.
- NUNCA deletar `email_log` ou `automation_logs`.
