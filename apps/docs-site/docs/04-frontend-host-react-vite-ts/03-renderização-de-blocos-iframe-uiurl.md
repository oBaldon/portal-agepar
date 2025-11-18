---
id: renderização-de-blocos-iframe-uiurl
title: "Renderização de blocos (iframe ui.url)"
sidebar_position: 3
---

Esta página descreve **como os blocos do catálogo são renderizados via `iframe`** no Host (React/Vite/TS), incluindo **políticas de sandbox**, **validação de URL**, **tamanhos responsivos**, **fallbacks** e um **canal opcional de postMessage**.

> Referências principais:  
> `apps/host/src/pages/CategoryView.tsx`, `apps/host/src/types.ts`, `apps/host/src/lib/catalog.ts`

---

## 1) Conceito

- Cada **bloco** tem uma `ui` que pode ser `{ type: "iframe", url }`.  
- O Host renderiza esse conteúdo **dentro de um `iframe`**, preservando **RBAC (ANY-of)** e **ordem** definida pelo catálogo.  
- Para **automations first-party** servidas pelo BFF (ex.: `/api/automations/.../ui`), costuma-se permitir uma sandbox “mais solta”.  
- Para **domínios externos**, aplicar sandbox **estrita** e validação de origem.

```mermaid
flowchart LR
  Host[Host React] -->|render| Iframe[Bloco Iframe]
  Iframe -->|carrega| BFF[BFF Automations UI]
````

---

## 2) Tipos relevantes (resumo)

```ts
// apps/host/src/types.ts (trecho)
export type CatalogBlock = {
  categoryId: string;
  ui:
    | { type: "iframe"; url: string }
    | { type: "link"; href: string };
  requiredRoles?: string[]; // ANY-of
  order?: number;
  hidden?: boolean;
};
```

---

## 3) Componente de bloco (iframe) — seguro por padrão

Regras implementadas abaixo:

* **Validação de URL** com `new URL(...)` e **allowlist** básica.
* **Sandbox dinâmica**:

  * **Externo** → sandbox **estrita** (sem `allow-same-origin`).
  * **First-party** (mesma origem do Host ou caminho `/api/automations/`) → sandbox **relaxada** controlada.
* **Fallback** quando `X-Frame-Options` bloquear ou quando falhar o carregamento.
* **Tamanho responsivo** com CSS e `minHeight` configurável.

```tsx
// apps/host/src/components/blocks/IframeBlock.tsx
import React, { useMemo, useRef, useState } from "react";
import type { CatalogBlock } from "../../types";

type Props = {
  block: CatalogBlock & { ui: { type: "iframe"; url: string } };
  minHeight?: number; // px
};

function isSameOrigin(url: URL) {
  try {
    return url.origin === window.location.origin;
  } catch {
    return false;
  }
}

function isLikelyAutomation(url: URL) {
  return url.pathname.startsWith("/api/automations/");
}

const EXTERNAL_ALLOWED_HOSTS = [
  // adicione domínios externos confiáveis se necessário
  // "exemplo.gov.br",
];

function isAllowedExternal(url: URL) {
  return EXTERNAL_ALLOWED_HOSTS.includes(url.hostname);
}

export default function IframeBlock({ block, minHeight = 600 }: Props) {
  const [failed, setFailed] = useState(false);
  const [loading, setLoading] = useState(true);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const target = useMemo(() => {
    try {
      return new URL(block.ui.url, window.location.origin);
    } catch {
      return null;
    }
  }, [block.ui.url]);

  if (!target) {
    return <div className="card error">URL inválida no bloco.</div>;
  }

  const sameOrigin = isSameOrigin(target);
  const firstPartyAutomation = sameOrigin || isLikelyAutomation(target);

  // Sandbox:
  // - Externo: estrito
  // - First-party: permitir scripts, forms e same-origin quando necessário
  const sandbox = firstPartyAutomation
    ? "allow-scripts allow-forms allow-same-origin"
    : "allow-scripts allow-forms";

  // Segurança extra para externos
  if (!firstPartyAutomation && !isAllowedExternal(target)) {
    return (
      <div className="card warning">
        Origem externa não permitida: <code>{target.href}</code>.{" "}
        <a href={target.href} target="_blank" rel="noreferrer">Abrir em nova aba</a>.
      </div>
    );
  }

  // onLoad: remove loading; se for cross-origin e vier em branco, exibimos fallback manual
  function handleLoad() {
    setLoading(false);
    // Heurística simples: se o iframe está carregado mas sem título/sem body, sugerir abrir em nova aba
    try {
      const doc = iframeRef.current?.contentDocument;
      if (doc && doc.body && doc.body.childElementCount === 0) {
        // pode ser bloqueio por X-Frame-Options; mantemos o iframe e mostramos aviso discreto
      }
    } catch {
      // cross-origin: acesso negado; ignorar
    }
  }

  // Observação: <iframe> não dispara onError de forma confiável; use timeout opcional
  React.useEffect(() => {
    const t = setTimeout(() => {
      if (loading) setFailed(true);
    }, 15000);
    return () => clearTimeout(t);
  }, [loading]);

  return (
    <div className="card iframe-block">
      {loading && <div className="muted">Carregando…</div>}
      {failed && (
        <div className="warning">
          Não foi possível embutir <code>{target.href}</code>.{" "}
          <a href={target.href} target="_blank" rel="noreferrer">Abrir em nova aba</a>.
        </div>
      )}
      <iframe
        ref={iframeRef}
        title={block.ui.url}
        src={target.href}
        onLoad={handleLoad}
        sandbox={sandbox}
        loading="lazy"
        allow="clipboard-read; clipboard-write"
        referrerPolicy="no-referrer"
        style={{ width: "100%", height: Math.max(minHeight, 400), border: 0 }}
      />
    </div>
  );
}
```

Estilos mínimos:

```css
/* apps/host/src/index.css (trechos) */
.card.iframe-block { padding: 0; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; }
.muted { color: #6b7280; padding: 8px; }
.warning { background: #fff7ed; border-left: 3px solid #f59e0b; padding: 8px 12px; }
```

---

## 4) Uso no `CategoryView`

```tsx
// apps/host/src/pages/CategoryView.tsx (trecho)
import IframeBlock from "../components/blocks/IframeBlock";

// ...
return (
  <div className="grid">
    {visible.map((b) =>
      b.ui.type === "iframe" ? (
        <IframeBlock key={b.ui.url} block={b} minHeight={600} />
      ) : (
        // outros tipos (link, placeholder)
        <a key={b.ui['href']} href={b.ui['href']} target="_blank" rel="noreferrer">Abrir</a>
      )
    )}
  </div>
);
```

---

## 5) Comunicação opcional via `postMessage`

Para automations que precisam **comunicar eventos** ao Host (ex.: “download pronto”):

### No iframe (página UI servida pelo BFF)

```js
// enviar evento ao host
window.parent?.postMessage({ kind: "automation:ready", payload: {/* ... */} }, "*");
```

### No Host

```ts
// apps/host/src/components/blocks/useIframeBus.ts
import { useEffect } from "react";
export function useIframeBus(handler: (e: MessageEvent) => void) {
  useEffect(() => {
    function onMsg(e: MessageEvent) {
      // TODO: validar origem (e.origin) se necessário
      handler(e);
    }
    window.addEventListener("message", onMsg);
    return () => window.removeEventListener("message", onMsg);
  }, [handler]);
}
```

> **Valide `e.origin`** para restringir quais origens podem enviar mensagens.

---

## 6) Testes e cURLs úteis

* Verificar se a UI da automation responde (via BFF):

```bash
# direta no BFF (porta 8000)
curl -i http://localhost:8000/api/automations/<slug>/ui
```

* Via Host (proxy):

```bash
curl -i http://localhost:5173/api/automations/<slug>/ui
```

Se a página retornar **`X-Frame-Options: DENY`**, o embutimento não será possível — use **link externo** como fallback.

---

## 7) Problemas comuns

* **Página não aparece no iframe**
  Alvo envia `X-Frame-Options: DENY` ou CSP que bloqueia `frame-ancestors`. Use fallback de link.

* **Conteúdo externo quebrando isolamento**
  Use sandbox **sem** `allow-same-origin` para externos e defina uma **allowlist** de domínios.

* **Scroll/altura ruim**
  Ajuste `minHeight` por bloco ou implemente **auto-resize** via `postMessage`.

* **RBAC bloqueando tudo**
  Confirme `requiredRoles` vs. `user.roles` e a filtragem antes de renderizar.

---

## Próximos passos

* **[Navbar por categorias e leitura do catálogo](./navbar-por-categorias-e-leitura-do-catálogo)**
* **Testes de integração** do fluxo catálogo → renderização → comunicação com automations.

---

> _Criado em 2025-11-18_


