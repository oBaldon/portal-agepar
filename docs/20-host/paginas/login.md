# Página: Login

A página de **Login** autentica o usuário via **/api/auth/login** e inicializa o estado global (usuário e catálogo).

---

## 🎯 Objetivos
- Capturar credenciais e chamar `POST /api/auth/login`.
- Armazenar cookie de sessão (HttpOnly) gerenciado pelo BFF.
- Carregar `/api/me` após sucesso e redirecionar para **Home**.

---

## Fluxo
1. Usuário preenche `username` e `password`.
2. Front envia `POST /api/auth/login` (JSON).
3. Se `200`, o BFF retorna usuário e define cookie.
4. Front chama `GET /api/me` e inicializa contexto `user`.
5. Redireciona para `/`.

---

## Exemplo (TSX)
```tsx
// apps/host/src/pages/Login.tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function Login() {
  const nav = useNavigate();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ username: u, password: p }),
      });
      if (!res.ok) throw new Error(`Login falhou: ${res.status}`);
      // opcional: fetch /api/me para popular contexto
      nav("/", { replace: true });
    } catch (e: any) {
      setErr("Usuário ou senha inválidos");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen grid place-items-center">
      <form onSubmit={onSubmit} className="w-full max-w-sm border rounded-2xl p-6 shadow-sm bg-white">
        <h1 className="text-xl font-semibold mb-4">Entrar</h1>
        <label className="block text-sm mb-1">Usuário</label>
        <input className="w-full border rounded-xl px-3 py-2 mb-3" value={u} onChange={e=>setU(e.target.value)} required />
        <label className="block text-sm mb-1">Senha</label>
        <input className="w-full border rounded-xl px-3 py-2 mb-4" type="password" value={p} onChange={e=>setP(e.target.value)} required />
        {err && <div className="text-sm text-red-600 mb-3">{err}</div>}
        <button disabled={loading} className="w-full rounded-2xl px-3 py-2 border shadow-sm hover:shadow">
          {loading ? "Entrando..." : "Entrar"}
        </button>
      </form>
    </div>
  );
}
````

---

## Erros & Segurança

* Mensagens genéricas (não revelar existência de usuário).
* Nunca logar senhas no front.
* Em produção, cookie `Secure` e `SameSite` adequados (ver BFF).

````

---

### `docs/20-host/paginas/home-dashboard.md`

```markdown
# Página: Home (Dashboard)

A **Home** lista **cards** de blocos disponíveis por **categoria**, com RBAC aplicado e ordem definida pelo catálogo.

---

## Conteúdo
- Título da categoria.
- Cards com `label` e `description` dos blocos.
- Link para a primeira rota (`routes[0]`) do bloco.

---

## Exemplo (TSX)
```tsx
// apps/host/src/pages/Home.tsx
import type { Catalog } from "../types/catalog";
import { userCanSeeBlock, User } from "../utils/rbac";
import { Link } from "react-router-dom";

export default function Home({ catalog, user }: { catalog: Catalog; user: User | null }) {
  const orderedCats = [...catalog.categories].sort(
    (a, b) => (a.order ?? Number.MAX_SAFE_INTEGER) - (b.order ?? Number.MAX_SAFE_INTEGER)
  );

  return (
    <div className="p-6 space-y-10">
      {orderedCats.map((cat) => {
        const blocks = catalog.blocks
          .filter((b) => b.categoryId === cat.id && !b.hidden && userCanSeeBlock(user, b))
          .sort((a, b) => (a.order ?? 999) - (b.order ?? 999));

        if (!blocks.length) return null;

        return (
          <section key={cat.id}>
            <h2 className="text-xl font-semibold mb-4">{cat.label}</h2>
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {blocks.map((b) => (
                <Link to={b.routes[0]} key={b.id} className="rounded-2xl border shadow-sm p-4 hover:shadow-md transition">
                  <div className="text-lg font-medium">{b.label}</div>
                  {b.description && <p className="text-sm text-gray-600 mt-1 line-clamp-2">{b.description}</p>}
                </Link>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}
````

---

## Acessibilidade

* Cards com texto descritivo.
* Foco e estados `:hover`/`:focus-visible` evidentes.

````

---

### `docs/20-host/paginas/category-view.md`

```markdown
# Página: Category View

Exibe todos os **blocos** de uma **categoria** específica. Útil quando a navegação por dropdown não é suficiente.

---

## Requisitos
- Receber `categoryId` via rota (ex.: `/categoria/:id`).
- Filtrar blocos por `categoryId` e **RBAC**.
- Preservar **ordem** (`order`|ordem de escrita).

---

## Exemplo (TSX)
```tsx
// apps/host/src/pages/CategoryView.tsx
import { useParams, Link } from "react-router-dom";
import type { Catalog } from "../types/catalog";
import { userCanSeeBlock, User } from "../utils/rbac";

export default function CategoryView({ catalog, user }: { catalog: Catalog; user: User | null }) {
  const { id } = useParams<{ id: string }>();
  const category = catalog.categories.find((c) => c.id === id);
  if (!category) return <div className="p-6">Categoria não encontrada.</div>;

  const blocks = catalog.blocks
    .filter((b) => b.categoryId === id && !b.hidden && userCanSeeBlock(user, b))
    .sort((a, b) => (a.order ?? 999) - (b.order ?? 999));

  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold mb-4">{category.label}</h1>
      {blocks.length === 0 ? (
        <div className="text-gray-600">Nenhum bloco disponível nesta categoria.</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {blocks.map((b) => (
            <Link to={b.routes[0]} key={b.id} className="rounded-2xl border shadow-sm p-4 hover:shadow-md transition">
              <div className="text-lg font-medium">{b.label}</div>
              {b.description && <p className="text-sm text-gray-600 mt-1 line-clamp-2">{b.description}</p>}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
````

---

## Breadcrumbs

* Derivar trilha com `navigation[]` do bloco/rota, ou `[ { path: '/categoria/:id', label: category.label } ]`.

````

---

### `docs/20-host/paginas/account-sessions.md`

```markdown
# Página: Account / Sessions

Página de **conta do usuário** com foco em **gestão de sessões** (futuro), integrando-se aos endpoints planejados no BFF.

---

## Funcionalidades
- Mostrar informações de sessão atual (IP aproximado, user agent, expiração).
- Listar **outras sessões ativas** (`GET /api/auth/sessions`) — **futuro**.
- Permitir encerrar sessão específica (`DELETE /api/auth/sessions/{id}`) — **futuro**.
- Botão **Logout** (`POST /api/auth/logout`).

---

## Exemplo (TSX)
```tsx
// apps/host/src/pages/AccountSessions.tsx
import { useEffect, useState } from "react";

type Sess = {
  session_id: string;
  created_at: string;
  expires_at: string;
  ip?: string;
  user_agent?: string;
};

export default function AccountSessions() {
  const [sessions, setSessions] = useState<Sess[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch("/api/auth/sessions", { credentials: "include" });
        if (!r.ok) throw new Error(String(r.status));
        setSessions(await r.json());
      } catch {
        setError("Falha ao carregar sessões (recurso futuro).");
      }
    })();
  }, []);

  async function doLogout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    location.href = "/login";
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-4">Sessões da Conta</h1>

      {error && <div className="text-sm text-gray-600 mb-3">{error}</div>}

      <div className="rounded-2xl border divide-y bg-white shadow-sm">
        {sessions.length === 0 && (
          <div className="p-4 text-gray-600">Sem dados de sessões (futuro).</div>
        )}
        {sessions.map((s) => (
          <div key={s.session_id} className="p-4 flex items-center justify-between gap-4">
            <div className="text-sm">
              <div><span className="font-medium">Sessão:</span> {s.session_id}</div>
              <div>Início: {new Date(s.created_at).toLocaleString()}</div>
              <div>Expira: {new Date(s.expires_at).toLocaleString()}</div>
              {s.ip && <div>IP: {s.ip}</div>}
              {s.user_agent && <div>Agente: {s.user_agent}</div>}
            </div>
            {/* Futuro: botão para encerrar sessão específica */}
            {/* <button className="rounded-xl border px-3 py-1">Encerrar</button> */}
          </div>
        ))}
      </div>

      <div className="mt-6">
        <button onClick={doLogout} className="rounded-2xl border px-4 py-2 shadow-sm hover:shadow">
          Sair da conta
        </button>
      </div>
    </div>
  );
}
````

---

## Considerações

* Em dev, `/api/auth/sessions` pode não existir — trate erro com mensagem clara.
* Em produção, garantir **`credentials: include`** nas requisições.
* Página deve ser **protegida** (usuário autenticado) e acessível via menu de conta.

