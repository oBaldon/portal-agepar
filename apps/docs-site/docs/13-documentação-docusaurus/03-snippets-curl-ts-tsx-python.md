---
id: snippets-curl-ts-tsx-python
title: "Snippets (cURL, TS/TSX, Python)"
sidebar_position: 3
---

Os exemplos de código da doc do Portal AGEPAR seguem um **padrão único**,
documentado no guia:

- `apps/docs-site/docs/15-apêndices/estilo-de-codigo.mdx`  
  (_Guia de Estilo — Exemplos de Código_)

Aqui a gente foca **nos três tipos de snippet mais usados**:

- cURL (para testar o BFF),
- TypeScript / TSX (Host),
- Python (BFF / automations),

com exemplos prontos para reaproveitar nas seções 01–12.

---

## 1) Convenções gerais (recap rápido do guia de estilo)

Resumo do que vale para todos os snippets:

- Sempre que fizer sentido, usar:

  ```md
  ```bash title="Alguma coisa importante" showLineNumbers
  # comando...
    ```

- Separar **comando** de **saída** em blocos diferentes.
- Usar nomes de arquivo/caminho reais no `title` (ex.:  
`title="apps/bff/app/automations/dfd.py"`).
- Para trechos longos, usar `showLineNumbers`.
- Preferir **idioma correto** no fence:
- `bash` para cURL/comandos,
- `ts` para TypeScript,
- `tsx` para componentes React,
- `python` para BFF/automations,
- `json`, `diff`, `text` conforme o caso.

---

## 2) Snippets de cURL

### 2.1. Padrões de uso

- Sempre marcar como `bash`.
- Quando for “comando oficial de teste”, incluir:
- `title="..."` com contexto (login, health, submit etc.),
- `showLineNumbers` se tiver mais de ~5 linhas.
- Usar `\` para quebra de linha e facilitar copy/paste.
- Usar URLs reais do BFF (`http://localhost:8000/...` em dev).

### 2.2. Exemplos prontos para reaproveitar

Login mock (do `README.md`):

```bash title="Login (mock, ambiente dev)" showLineNumbers
curl -i -X POST http://localhost:8000/api/auth/login \
-H 'Content-Type: application/json' \
-d '{"identifier":"dev@example.com","password":"dev"}'
````

Sessão atual:

```bash title="Sessão atual (/api/me)" showLineNumbers
curl -i http://localhost:8000/api/me
```

Automação simples (form2json):

```bash title="Submit em /api/automations/form2json/submit" showLineNumbers
curl -i -X POST http://localhost:8000/api/automations/form2json/submit \
  -H 'Content-Type: application/json' \
  -d '{
    "fullName": "  Maria da Silva  ",
    "email": "  maria@example.com ",
    "phone": "(41) 9 9999-0000",
    "acceptTerms": "sim",
    "amount": "1.234,56",
    "dateStart": "18/11/2025"
  }'
```

Esses exemplos aparecem (ou podem aparecer) em:

* 02 — Ambiente & Dev Setup,
* 06 — BFF (FastAPI),
* 07 — Automations,
* 12 — Testes.

---

## 3) Snippets TypeScript (Host)

### 3.1. Padrões de uso

* Usar `ts` para código “puro” (helpers, API, tipos).

* Usar `tsx` apenas para componentes React com JSX.

* Manter o **caminho relativo real** no `title`:

  * `title="apps/host/src/lib/api.ts"`
  * `title="apps/host/src/types.ts"`

* Em exemplos de API, mostrar **funções completas** e não pedaços soltos,
  para facilitar reaproveitamento.

### 3.2. Exemplo: helper de API com JSON tipado

Trecho real de `apps/host/src/lib/api.ts`:

```ts title="apps/host/src/lib/api.ts — jsonOrThrow" showLineNumbers
async function jsonOrThrow<T>(
  res: Response,
  opts?: { suppress401?: boolean; suppress403?: boolean }
): Promise<T> {
  await ensureOkOrThrow(res, opts);
  const ct = res.headers.get("content-type") || "";
  if (!ct.toLowerCase().includes("application/json")) {
    // @ts-expect-error – pode ser vazio/null quando o caller não espera corpo
    return null;
  }
  return (await res.json()) as T;
}
```

Exemplo de uso em um endpoint simples:

```ts title="apps/host/src/lib/api.ts — getMe()" showLineNumbers
export async function getMe(): Promise<User> {
  const res = await fetch(`${API_BASE}/me`, {
    method: "GET",
    credentials: "include",
  });
  return await jsonOrThrow<User>(res);
}
```

> Esses snippets são bons candidatos para aparecer em:
>
> * 04 — Frontend Host (React/Vite/TS),
> * 11 — Padrões de Erro & DX (lado do Host),
> * 12 — Testes (exemplo de como testar chamadas de API).

---

## 4) Snippets TSX (componentes React)

### 4.1. Padrões de uso

* Usar `tsx` com `title="..."`.
* Favor mostrar componentes **pequenos** e focados:

  * página de exemplo,
  * card de automação,
  * uso de hooks (`useAuth`, `useCatalog`).
* Quando for playground interativo, usar ` ```tsx live ... ``` `
  (normalmente em `.mdx`, como em `playground-react.mdx`).

### 4.2. Exemplo simples de componente

```tsx title="Exemplo de componente simples" showLineNumbers
type Props = { title: string };

export function SectionTitle({ title }: Props) {
  return <h2 className="text-xl font-semibold mb-2">{title}</h2>;
}
```

Este tipo de snippet aparece bem em:

* 04 — Frontend Host (layout e componentes),
* 15 — Apêndices (`playground-react.mdx`).

---

## 5) Snippets Python (BFF / automations)

### 5.1. Padrões de uso

* Sempre marcar como `python`.

* Usar `title` com o **caminho real** dentro de `apps/bff`:

  * `title="apps/bff/app/automations/dfd.py"`,
  * `title="apps/bff/app/main.py"`.

* Preferir mostrar:

  * assinatura completa de endpoints (`@router.get/post/...`),
  * modelos Pydantic com `ConfigDict`,
  * helpers compartilhados (`err_json`, normalização, etc.).

### 5.2. Exemplo: endpoint de submit em automação

Trecho real de `apps/bff/app/automations/dfd.py` (início da função):

```python title="apps/bff/app/automations/dfd.py — POST /submit" showLineNumbers
@router.post("/submit")
async def submit_dfd(
    request: Request,
    body: Dict[str, Any],
    background: BackgroundTasks,
    user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES)),
):
    """
    Recebe uma submissão de DFD, valida dados e agenda o processamento em background.

    Fluxo
    -----
    - Normaliza payload bruto e valida com `DfdIn`.
    - Checa duplicidade por `numero` e `protocolo`.
    - Cria submissão `queued`, audita `submitted` e agenda `_process_submission`.
    """
    raw = {
        "modeloSlug": none_if_empty(body.get("modeloSlug")),
        "numero": (body.get("numero") or "").strip(),
        "assunto": (body.get("assunto") or "").strip(),
        "pcaAno": (body.get("pcaAno") or "").strip(),
        "protocolo": (body.get("protocolo") or "").strip(),
        # ...
    }
    # validação + persistência seguem abaixo...
```

Esse padrão é reutilizado em:

* 06 — BFF (FastAPI),
* 07 — Automations (padrão de módulos),
* 08 — Banco & Persistência,
* 11 — Padrões de Erro & DX.

---

## 6) Snippets combinando cURL + TS + Python

Quando queremos mostrar **o mesmo fluxo em 3 camadas** (cURL → Host → BFF),
a recomendação (detalhada em `15-apêndices/estilo-de-codigo.mdx`) é usar
**abas** (`Tabs`/`TabItem`) em um arquivo `.mdx`.

Exemplo de trechinho MDX (para ser usado em `.mdx`, não aqui):

````mdx title="Exemplo de Tabs para cURL/TS/Python" showLineNumbers
import Tabs from '@theme/Tabs';
import TabItem from '@theme/TabItem';

<Tabs>
  <TabItem value="curl" label="cURL">
    ```bash
    curl -i -X POST http://localhost:8000/api/automations/dfd/submit \
      -H "Content-Type: application/json" \
      -d '{"modeloSlug":"padrao","numero":"2025-001","protocolo":"12345/2025","assunto":"...","pcaAno":"2025"}'
    ```
  </TabItem>
  <TabItem value="ts" label="TypeScript (Host)">
    ```ts
    const res = await fetch("/api/automations/dfd/submit", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    const data = await jsonOrThrow<{ sid: string; status: string }>(res);
    ```
  </TabItem>
  <TabItem value="py" label="Python (BFF)">
    ```python
    @router.post("/submit")
    async def submit_dfd(...):
        body = DfdIn(**normalize_payload(raw))
        sid = await create_submission(body, user)
        return {"sid": sid, "status": "queued"}
    ```
  </TabItem>
</Tabs>
````

> Dica: use esse padrão principalmente em:
>
> * 06 — BFF,
> * 07 — Automations,
> * 11 — Padrões de Erro & DX,
> * 12 — Testes (quando quiser mostrar API + client).

---

## 7) Checklist rápido para novos snippets

Quando for escrever uma nova página ou exemplo:

* [ ] Escolhi **o idioma correto** (`bash`, `ts`, `tsx`, `python`, `json`, `diff`).
* [ ] Usei `title="..."` com caminho/descrição útil.
* [ ] Usei `showLineNumbers` para blocos mais longos.
* [ ] Evitei misturar comando e saída no mesmo bloco.
* [ ] Reaproveitei trechos **reais** do monorepo quando possível.
* [ ] Para exemplos multi-linguagem, considerei usar Tabs em `.mdx`.

---

> _Criado em 2025-12-01_
