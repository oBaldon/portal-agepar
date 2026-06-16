---
id: "automacao-ponto-saldo-pdf"
title: "Automação — Saldo de Horas (PDF)"
sidebar_position: 8
---

## Visão geral

A automação **Saldo de Horas (PDF)** lê um **espelho de ponto em PDF** (um mês) e devolve:

- total **esperado** no mês (considerando dias úteis vs fim de semana vs feriado/ponto facultativo *conforme o PDF*)
- total **creditado**
- **faltante total**, **sobrante total** e **saldo líquido**
- sugestão de **plano uniforme** (a partir de **hoje**) para **zerar o mês**, sem arredondar minutos

### Universo = PDF

Esta automação **não usa calendário externo**.
Ou seja:
- **feriados** e **ponto facultativo** só são considerados se estiverem marcados no próprio PDF.

---

## Regras de cálculo

### Esperado (por dia)

- Sábado/Domingo → **0**
- Se o PDF marcar **FERIADO** → **0**
- Se o PDF marcar **PONTO FACULTATIVO** → **0**
- Demais dias → **08:00** (480 min)

### Creditado (por dia)

Ordem de prioridade:

1. **Coluna "Resultado"** (HH:MM) → é a fonte principal
2. Se não existir "Resultado": **Trabalhadas + Justificadas**
3. Se não houver números, mas houver texto de **ATESTADO** ou **LICENÇA** → credita **08:00**
4. Caso contrário → **0** (e o dia é marcado como `MISSING_DATA`)

---

## Plano (planner)

- O planner considera apenas **dias úteis futuros** a partir de **hoje** (timezone SP).
- Exclui feriados e ponto facultativo marcados no PDF.
- Distribui o saldo **uniformemente**:
  - se está faltando → sugere **adicionar** minutos por dia
  - se está sobrando → sugere **reduzir** minutos por dia
- **Sem arredondamento**: distribuição exata em minutos inteiros.

> Observação: a UI pode emitir alertas se o ajuste por dia ficar acima de uma recomendação “saudável” (ex.: 2h/dia), mas não bloqueia.

---

## Endpoints

Base: `/api/automations/ponto_saldo`

- `GET /schema`
- `GET /ui` (iframe)
- `POST /submit` (multipart/form-data com `pdf`)
- `GET /submissions`
- `GET /submissions/{id}`
- `POST /submissions/{id}/download` (JSON)

---

## Teste rápido (manual)

1. Acessar a UI:
   - `GET /api/automations/ponto_saldo/ui`
2. Subir um PDF do espelho de ponto.
3. Verificar:
   - totais (esperado/creditado/faltante/sobrante)
   - lista de dias com marcações (feriado/pf/atestado/licença)
   - plano sugerido (a partir de hoje)

---

## Limitações

- PDFs “escaneados” (sem texto extraível) podem falhar ou retornar alertas indicando necessidade de OCR.
- Como o **PDF é o universo**, feriados não marcados no documento não serão inferidos.
- Caso o PDF tenha layout muito diferente, a extração pode não conseguir identificar linhas no padrão `dd/mm - ...`.

## Arquivos mapeados

- `apps/bff/app/automations/ponto_saldo.py`
- `catalog/catalog.dev.json`

## Observações

- O bloco está no catálogo da categoria `pessoas`.
- O acesso é restringido a papéis como `ca`, `rh` e `cof`.
