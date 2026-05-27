# Design: Regras de Extração por Site

**Data:** 2026-05-27  
**Status:** Aprovado  
**Contexto:** Bug identificado — artigo "Transfira pontos Esfera e garanta status Gold ALL Accor" foi classificado como `transfer_bonus esfera→smiles, 48%` incorretamente. Root cause: `str.find("gol")` casa dentro de "Gold", e `bonus_pct != None` sempre resultava em `transfer_bonus`.

---

## Problema

O extractor atual é genérico para todos os sites. Isso causa:

1. **Word boundary bug**: `_find_programs` usa `str.find(key)` sem boundary — `"gol"` (→ smiles) casa dentro de `"Gold"`, `"algoritmo"`, etc.
2. **Classificação permissiva de `transfer_bonus`**: qualquer `bonus_pct` vira `transfer_bonus`, mesmo bônus de hotel, acúmulo ou compra de milhas.
3. **Sem contexto por site**: sites têm vocabulários distintos — o que é `flight_award` no PPV ("Alerta de passagens PPV") é opaco para o extractor genérico.

---

## Objetivo

Classificar promoções com alta confiança por tipo (`transfer_bonus`, `flight_award`, `other`), usando padrões específicos de cada site RSS, mantendo custo zero (sem LLM) e a arquitetura existente.

**Critério de sucesso:**
- `transfer_bonus` e `flight_award` sem falsos positivos.
- `other` pode ser mais permissivo.
- O artigo ALL Accor passa a ser `other` com `origin_program=esfera`, `destination_program=None`.

---

## Arquitetura

### Novo arquivo: `src/pipeline/site_rules.py`

Define um `SiteRule` dataclass e um dicionário `SITE_RULES: dict[str, SiteRule]` com uma entrada por `feed_source` (chave do `signal.extra["feed_source"]`).

```python
@dataclass
class SiteRule:
    confirm_flight_award:   list[re.Pattern]  # qualquer match → flight_award
    confirm_transfer_bonus: list[re.Pattern]  # qualquer match → transfer_bonus
    confirm_accumulation:   list[re.Pattern]  # qualquer match → other (acúmulo)
    reject_transfer_bonus:  list[re.Pattern]  # qualquer match → não pode ser transfer_bonus
```

### Modificado: `src/pipeline/extractor.py`

**Fix 1 — `_find_programs` com word boundaries:**
```python
# Antes (buggy):
pos = lower.find(key)

# Depois:
pattern = _PROGRAM_RE_CACHE.setdefault(key, re.compile(rf"\b{re.escape(key)}\b"))
m = pattern.search(lower)
```

**Fix 2 — nova função `_classify_promo_type`:**

Fluxo de prioridade:
```
1. site confirm_flight_award match?   → "flight_award"
2. site confirm_transfer_bonus match? → "transfer_bonus"
3. site confirm_accumulation match?   → "other"
4. site reject_transfer_bonus match?  → bloqueia transfer_bonus nas etapas seguintes
5. explicit direction (X→Y) + transfer keyword + bonus_pct? → "transfer_bonus"
6. flight_award genérico (IATA×2 + milhas / "milhas o trecho" / "milhas + taxas")? → "flight_award"
7. fallback → "other"
```

**Fix 3 — `transfer_bonus` genérico agora exige 3 condições simultâneas:**
- Direção explícita detectada por `_find_transfer_direction` OU `_TRANSFER_KEYWORD_RE` no texto
- Dois programas rastreados identificados
- `bonus_pct` presente

**Fix 4 — exclusões globais aplicadas antes da classificação genérica:**
- `"compra (direta )?de milhas"` → bloqueia `transfer_bonus`
- `"pontos por real"` / `"por real gasto"` → bloqueia `transfer_bonus`

---

## Regras por Site

### `pontos_pra_voar`

| Tipo | Padrões |
|---|---|
| `confirm_flight_award` | `"alerta de passagens ppv"`, `r"\d+\s*milhas\s*\+\s*taxas"`, `r"\b[A-Z]{3}\b.{0,10}\b[A-Z]{3}\b"` (dois IATAs próximos) |
| `confirm_transfer_bonus` | `r"b[oô]nus.*transfer[eê]ncia de .+ para .+"`, `r"transfer[eê]ncia.*\d+%"` |
| `confirm_accumulation` | `r"\d+\s+pontos\s+por\s+real"`, `r"\d+\s+pontos\s+por\s+d[oó]lar"` |
| `reject_transfer_bonus` | `r"status\s+gold"`, `r"b[oô]nus\s+em\s+pontos\s+reward"`, `r"pontos\s+reward"` |

### `melhores_cartoes`

| Tipo | Padrões |
|---|---|
| `confirm_flight_award` | `r"\d+[\.,]?\d*\s+milhas\s+o\s+trecho"`, `r"a\s+partir\s+de\s+\d+\s+milhas"`, `r"promo[çc][aã]o\s+de\s+final\s+de\s+semana"` |
| `confirm_transfer_bonus` | `r"b[oô]nus\s+na\s+transfer[eê]ncia"`, `r"transfer[eê]ncia\s+de\s+.+\s+para\s+.+"` |
| `reject_transfer_bonus` | `r"compra\s+(direta\s+)?de\s+milhas"`, `r"comprar\s+milhas"`, `r"cashback"` |

### `mestre_das_milhas`

| Tipo | Padrões |
|---|---|
| `confirm_flight_award` | `r"\d+\s+milhas\s+o\s+trecho"`, `r"\d+\s+milhas\s+por\s+trecho"` |
| `confirm_transfer_bonus` | `r"b[oô]nus.*transfer[eê]ncia"`, `r"transfer[eê]ncia.*\d+%"` |
| `confirm_accumulation` | `r"\d+\s+pontos\s+por\s+real"`, `r"\d+\s+pontos\s+por\s+d[oó]lar"` |
| `reject_transfer_bonus` | `r"compra\s+de\s+milhas"`, `r"an[aá]lise"`, `r"parceria"` |

### `melhores_destinos`

| Tipo | Padrões |
|---|---|
| `confirm_flight_award` | `r"\d+\s+milhas\s+o\s+trecho"`, `r"milhas\s+\+\s+taxas"`, `r"a\s+partir\s+de\s+\d+\s+milhas"` |
| `confirm_transfer_bonus` | `r"b[oô]nus.*transfer[eê]ncia\s+de\s+.+\s+para\s+.+"` |
| `reject_transfer_bonus` | *(nenhuma — usa apenas regras genéricas globais)* |

### `passageiro_de_primeira`

Feed retornou 403 durante análise — sem amostras diretas. Usa regras genéricas melhoradas com `reject_transfer_bonus` conservador:

| Tipo | Padrões |
|---|---|
| `reject_transfer_bonus` | `r"compra\s+de\s+milhas"`, `r"status\b"`, `r"\bhotel\b"` |

> **Nota:** Refinar após obter amostras reais de artigos do Passageiro de Primeira.

---

## Testes

Arquivo: `tests/unit/test_extractor_site_rules.py`

| Caso | Site | Sinal de entrada | Resultado esperado |
|---|---|---|---|
| Regressão ALL Accor | `pontos_pra_voar` | título "status Gold ALL Accor", body com "48% bônus em pontos Reward" | `other`, `destination_program=None` |
| Alerta PPV | `pontos_pra_voar` | "Alerta de passagens PPV… 3.040 milhas + taxas" | `flight_award` |
| Acúmulo Esfera | `pontos_pra_voar` | "18 pontos por real gasto" | `other` |
| Compra de milhas | `melhores_cartoes` | "365% de bônus na compra direta de milhas Smiles" | `other` |
| Flight MC | `melhores_cartoes` | "3.262 milhas o trecho LATAM Pass" | `flight_award` |
| Transfer real | qualquer | "80% de bônus na transferência de Livelo para Smiles" | `transfer_bonus`, `origin=livelo`, `dest=smiles` |
| Word boundary `gol` | qualquer | texto com "Gold" mas sem "Gol " | `smiles` não detectado em `programs` |
| Acúmulo MDM | `mestre_das_milhas` | "10 pontos por real com ofertas de viagem" | `other` |

---

## Arquivos Alterados

| Arquivo | Tipo |
|---|---|
| `src/pipeline/site_rules.py` | Novo |
| `src/pipeline/extractor.py` | Modificado |
| `tests/unit/test_extractor_site_rules.py` | Novo |

---

## Fora de Escopo

- Alterações em `news_monitor.py`, `dispatcher.py`, `dedup.py`
- Mudanças de schema no banco
- Regras para programas fora dos 5 rastreados (ALL Accor, Marriott, etc.) — continuam como `other`
- Migração de promoções já gravadas incorretamente no banco
