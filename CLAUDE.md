# Miles Radar — CLAUDE.md

## 1. Contexto do projeto

**Objetivo:** Monitorar promoções de transferência e acúmulo de milhas nos programas brasileiros (Smiles, Azul, LATAM, Livelo, Esfera, Iupp), filtrar pelas combinações de cada usuário e enviar e-mails de alerta em até 3 dias por promoção ativa. **Custo operacional alvo: zero (exceto hospedagem).**

**Gatilhos:** Cron em 6 horários/dia (06h, 09h, 12h, 15h, 18h, 21h BRT). O scan das 12h envia e-mail de rotina; demais scans enviam apenas se nova promoção for detectada.

**Criticidade:** Média. Atraso de até 1h é aceitável. Meta: capturar toda promoção dentro da janela de 1h após lançamento.

---

## 2. Stack e ambiente

**Runtime:** Python 3.12

**Bibliotecas chave:**
- `playwright` + `playwright-stealth` — scraping JS-heavy e visual diff
- `cloudscraper` — bypass de Cloudflare nos domínios dos programas
- `httpx` — HTTP assíncrono para sitemaps, RSS e APIs públicas
- `beautifulsoup4` + `lxml` — parsing HTML
- `feedparser` — RSS e Atom feeds
- `imagehash` — perceptual hash para visual diff
- `pydantic v2` — validação de schemas
- `apscheduler` — agendamento de scans e e-mails
- `sqlalchemy 2` + `alembic` — ORM e migrações (Supabase via connection string)
- `supabase-py` — auth de usuários
- `jinja2` — templates HTML de e-mail

**Integrações externas (todas gratuitas):**
- Programas: Smiles, Azul, LATAM, Livelo, Esfera, Iupp — sem auth. Livelo e Esfera às vezes expõem endpoints JSON públicos mais estáveis que o HTML — verificar antes de scraping.
- Notícias: Melhores Destinos, Passageiro de Primeira, Melhores Cartões, Pontos pra Voar, Mestre das Milhas — RSS preferido, scraping como fallback
- Google News RSS — `news.google.com/rss/search?q=...&hl=pt-BR` — sem auth
- crt.sh, DNS público — sem auth
- Google Search Console — service account (opcional, ver `@docs/setup-search-console.md`)
- **E-mail:** Resend (3.000/mês) — preferido. Gmail SMTP (500/dia) como fallback.
- **Banco:** Supabase free tier (PostgreSQL 500MB) · **Erros:** Sentry free tier

**Sem LLM na pipeline.** Extração por regex + seletores CSS em `src/processor/extractor.py`.

---

## 3. Estrutura do repositório

```
/src
  /monitors              # 1 arquivo por método — todos retornam list[RawSignal]
    direct_scraper.py    # Tier 1 — landing pages dos programas (cloudscraper + BS4)
    hash_diff.py         # Tier 1 — HTML hash diff por URL monitorada
    rss_monitor.py       # Tier 1 — RSS dos sites de notícias de milhas
    google_news.py       # Tier 1 — Google News RSS por keyword
    sitemap_monitor.py   # Tier 2 — sitemap.xml dos programas
    robots_monitor.py    # Tier 2 — robots.txt dos programas
    news_scraper.py      # Tier 2 — scraping direto de notícias sem RSS
    search_console.py    # Tier 2 — opcional
    url_fuzzer.py        # Tier 3 — URL pattern fuzzing por histórico
    visual_diff.py       # Tier 3 — screenshot comparison (Playwright stealth)
    ct_logs.py           # Tier 3 — Certificate Transparency via crt.sh
    dns_monitor.py       # Tier 3 — novos subdomínios dos programas
  /processor
    extractor.py         # regex + seletores por programa → Promotion estruturada
    dedup.py             # fingerprint → dedup antes de qualquer escrita no DB
    preference_filter.py # filtra Promotions pelas preferências do usuário
  /config
    settings.py          # pydantic-settings — URLs, thresholds, intervalos de tier
  /api                   # FastAPI — site de preferências do usuário
  /email
    dispatcher.py        # decide se/quando enviar; consulta email_log
    sequence.py          # controla sequência de 3 dias por (promo_id, user_id)
    /templates           # day1.html, day2.html, day3.html + partials (Jinja2)
  /scheduler/jobs
    tier1.py             # jobs dos 6 scans diários
    tier2.py             # jobs dos scans de 09h e 18h
    tier3.py             # job do scan de 06h
  /db
    models.py · /migrations  # Alembic
/tests
  /unit · /integration
  /fixtures              # HTMLs e RSS reais para mocks; screenshots via Git LFS
/scripts
  backfill_promos.py     # reprocessar sinais históricos — exige --dry-run
```

---

## 4. Comandos essenciais

```bash
# Setup
pip install -r requirements.txt && playwright install chromium && alembic upgrade head

# Desenvolvimento
python -m src.scheduler.jobs --dry-run    # 1 ciclo completo, sem e-mails reais
uvicorn src.api.main:app --reload

# Qualidade (obrigatório antes de concluir qualquer tarefa)
ruff check . && ruff format --check . && mypy src

# Testes
pytest tests/unit
pytest tests/integration                  # requer .env com Supabase de teste
pytest tests/unit/test_dedup.py          # preferir durante desenvolvimento

# Operacional
python scripts/backfill_promos.py --dry-run
```

---

## 5. Fluxo de trabalho

**Antes de codar:** ler o arquivo relacionado — nunca inferir estrutura. Tarefas não-triviais: apresentar plano e aguardar confirmação. Um objetivo por PR.

**Ao implementar:** seguir padrões do arquivo editado, adicionar/atualizar testes para toda lógica de negócio tocada, rodar `ruff check . && mypy src && pytest tests/unit` antes de declarar concluído.

---

## 6. Regras críticas

<critical_rules>

### RSS/API antes de scraping HTML
Verificar `/feed` ou `/rss` antes de criar qualquer scraper HTML para blogs. Para programas, verificar endpoint JSON público antes de scraping. Scraping HTML é o método mais frágil — usar apenas quando não há alternativa.

### Sem LLM — extração por regras
`src/processor/extractor.py` usa regex e seletores CSS por programa. **NUNCA** adicionar chamada à Anthropic, OpenAI ou qualquer LLM. Se um programa mudar layout, atualizar os seletores — não introduzir LLM como atalho.

### Anti-bloqueio de IP (não-negociável)
- Intervalo mínimo **15–30s aleatório** entre requisições ao **mesmo domínio** no mesmo scan.
- `cloudscraper` para os 6 programas. `httpx` apenas para sitemaps, RSS, crt.sh e APIs públicas.
- Playwright **sempre com stealth** em domínios de programa. Nunca sem.
- User-Agent rotacionado por scan via `src/integrations/user_agents.py`.
- **NUNCA** paralelizar requisições ao mesmo domínio. Concorrência apenas entre domínios distintos.
- 429 ou 403: `monitor_state.blocked_until = now() + 2h` — pular até cooldown.

### Supabase free tier — keepalive obrigatório
Pausa após 7 dias sem atividade. Keepalive (`SELECT 1` a cada 5 dias) é responsabilidade de cron externo (GitHub Actions) — sem script no repo. **NUNCA** assumir banco ativo sem verificar conexão no início de cada job.

### Idempotência de promoções
- Transferência: `sha256(source_program + dest_program + bonus_pct + start_date)`
- Acúmulo: `sha256(program + multiplier + trigger + start_date)`

Múltiplos monitores capturando a mesma promo = **1 linha no DB**. `dedup.py` roda antes de qualquer escrita e antes de acionar o dispatcher.

### Sequência de e-mails (3 dias)
- **Dia 1:** disparo imediato na primeira detecção (ou consolidado no scan das 12h).
- **Dia 2 e 3:** exatamente 24h e 48h após Dia 1, via APScheduler one-shot jobs agendados no Dia 1.
- `email_log(user_id, promo_id, day_number, sent_at)` é a fonte da verdade — verificar antes de qualquer envio.
- **NUNCA** enviar Dia 2/3 se `promotion.valid_until < now()`. Prorrogação de end_date não reinicia a sequência.

### Envio de e-mail somente com promoção ativa
**NUNCA** enviar e-mail vazio. Verificar: `promotion.valid_until >= now()` **E** `promotion matches user_preferences`. Múltiplas promoções no mesmo scan = **1 e-mail consolidado** por usuário.

### Tier de execução
- **Tier 1** (todos os 6 scans): `direct_scraper`, `hash_diff`, `rss_monitor`, `google_news`
- **Tier 2** (09h e 18h): + `sitemap_monitor`, `robots_monitor`, `news_scraper`, `search_console`
- **Tier 3** (06h apenas): + `url_fuzzer`, `visual_diff`, `ct_logs`, `dns_monitor`

Mudança neste calendário: atualizar `src/scheduler/jobs/tier{1,2,3}.py` **e** esta seção simultaneamente.

### Segredos
**NUNCA** commitar `.env`. Variáveis obrigatórias: `SUPABASE_URL`, `SUPABASE_KEY`, `DATABASE_URL`, `RESEND_API_KEY` (ou `GMAIL_APP_PASSWORD`), `SENTRY_DSN`. Credencial hardcoded detectada: parar e avisar.

### Produção
- **NUNCA** rodar `backfill_promos.py` sem `--dry-run` primeiro.
- **NUNCA** apagar registros de `email_log`.
- Todo schema change via Alembic migration versionada. Zero `ALTER TABLE` manual.

</critical_rules>

---

## 7. Convenções de domínio

- Par de transferência é **ordenado e não-comutativo**: `Esfera→Smiles ≠ Smiles→Esfera`. Modelar como `(source: str, dest: str)`.
- Funções de monitor: prefixo `scan_` (ex: `scan_sitemap`, `scan_landing_page`).
- Toda requisição HTTP passa por `src/integrations/http_client.py`. **Nunca** chamar `httpx` ou `cloudscraper` diretamente num monitor.
- Seletores CSS e regex por programa em `src/processor/extractor.py` → dicionário `PROGRAM_RULES`. Atualizar lá e apenas lá.
- Lógica de apresentação não entra em Python — templates em `src/email/templates/`.

---

## 8. Testes

Unitário cobre: dedup (fingerprint), sequência de 3 dias, filtros de preferência e extractor por programa (fixtures de HTML/RSS reais — nunca inventar response). Integração testa fluxo ponta a ponta com Supabase de projeto de teste dedicado. Mocks obrigatórios para toda HTTP call e envio de e-mail nos testes unitários.

**Cobertura mínima:** 85% em `src/processor/` e `src/email/`. **DoD:** `ruff check . && mypy src && pytest tests/unit` passando.

---

## 9. Referências

- `@README.md` — visão geral
- `@src/db/schema.sql` — schema do banco
- `@docs/programs.md` — URLs, seletores CSS e padrões de URL por programa
- `@docs/news-sources.md` — RSS endpoints e seletores das fontes de notícias
- `@docs/decisions/` — decisões de arquitetura
- `@docs/runbooks/` — runbooks operacionais
