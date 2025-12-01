---
id: rbac-no-host-any-of
title: "RBAC no Host (ANY-of)"
sidebar_position: 4
---

No Portal AGEPAR, o Host (React/Vite) aplica um **RBAC de vitrine** em cima do catálogo:

- **Quem pode ver o quê** na UI (cards, categorias, rotas) é decidido no frontend,
- com base em:
  - `user.roles` (dados de `/api/me`),
  - `block.requiredRoles` e `block.superuserOnly`,
  - `category.requiredRoles`.

O modelo é **ANY-of**:

> Se um bloco ou categoria define `requiredRoles`, basta o usuário ter **ao menos um** desses papéis.  
> `admin` e `is_superuser=true` sempre enxergam tudo.

> Referências principais no repositório:  
> `apps/host/src/types.ts`  
> `apps/host/src/lib/catalog.ts`  
> `apps/host/src/App.tsx`  
> `apps/host/src/pages/HomeDashboard.tsx`  
> `apps/host/src/pages/CategoryView.tsx`  
> `apps/bff/app/auth/rbac.py` (RBAC no BFF, para comparação)

---

## 1) De onde vêm os roles e como aparecem no Host

### 1.1. Campo `roles` no tipo `User`

`apps/host/src/types.ts`:

```ts title="User — roles e superuser"
export type User = {
  cpf: string | null;
  nome: string;
  email: string | null;
  roles: string[];
  unidades: string[];
  /** Mecanismo de auth atual ("mock" apenas em DEV). */
  auth_mode?: AuthMode;
  is_superuser?: boolean;
  /**
   * Quando true, o servidor exige troca de senha antes de permitir navegação.
   * Retornado por /api/auth/login e /api/me.
   */
  must_change_password?: boolean;
};
````

Esses campos vêm do BFF:

* `roles` — array de strings (ex.: `["user","compras","pregoeiro"]`);
* `is_superuser` — flag especial (bypass de RBAC);
* `auth_mode` — `local | oidc | mock` (útil para saber se a sessão é “mock de dev”).

### 1.2. Roles no catálogo — categorias e blocos

Ainda em `types.ts`, o catálogo define RBAC por categoria e por bloco:

```ts title="Category.requiredRoles" showLineNumbers
export type Category = {
  id: string;
  label: string;
  icon?: string;
  order?: number;
  hidden?: boolean;
  /** RBAC ANY-of para a categoria (além do RBAC por bloco). */
  requiredRoles?: string[];
};
```

```ts title="Block.requiredRoles e superuserOnly" showLineNumbers
export type Block = {
  name: string;
  displayName?: string;
  version: string;
  // ...
  categoryId: string;
  description?: string;
  hidden?: boolean;
  /**
   * RBAC ANY-of: se definido, o usuário precisa ter pelo menos um dos roles.
   * A checagem é feita na UI.
   */
  requiredRoles?: string[];
  /** Se true, apenas superusers visualizam (admin não basta). */
  superuserOnly?: boolean;
};
```

Resumindo:

* **Categoria** pode exigir roles (`Category.requiredRoles`).
* **Bloco** também pode exigir roles (`Block.requiredRoles`) e/ou marcar `superuserOnly`.
* O Host sempre aplica RBAC **no nível do bloco** e, depois, **no nível da categoria**.

---

## 2) Função central: `userCanSeeBlock` (ANY-of)

Toda decisão de visibilidade de blocos passa por:

```ts title="apps/host/src/types.ts — userCanSeeBlock" showLineNumbers
export function userCanSeeBlock(user: User | null, block: Block): boolean {
  if (block.hidden) return false;
  if (block.superuserOnly) {
    return !!(user && user.is_superuser === true);
  }
  const required = block.requiredRoles ?? [];
  if (required.length === 0) return true;
  if (!user) return false;

  const userRoles = new Set((user.roles || []).map((r) => r.trim().toLowerCase()));
  if (user.is_superuser || userRoles.has("admin")) return true;

  return required.some((r) => userRoles.has(r.trim().toLowerCase()));
}
```

Regras, em ordem:

1. **`hidden`**

   * Se `block.hidden === true`, ninguém vê (nem superuser).
2. **`superuserOnly`**

   * Se `block.superuserOnly === true`, só `user.is_superuser === true` enxerga.
   * `admin` **não basta** para esse caso.
3. **Sem `requiredRoles`**

   * Se `requiredRoles` vazio/indefinido → bloco é público para qualquer usuário logado.
4. **Usuário não logado**

   * Se há `requiredRoles` mas `user` é `null` → não enxerga.
5. **Bypass para `admin` e superuser**

   * Se `user.is_superuser` ou `roles` contém `"admin"` → vê tudo (exceto `hidden` ou `superuserOnly`).
6. **ANY-of**

   * Caso geral:

     * normaliza `roles` do usuário (`trim().toLowerCase()`),
     * normaliza `requiredRoles`,
     * retorna `true` se **algum** `required` estiver presente em `userRoles`.

Exemplo:

* `block.requiredRoles = ["compras", "coordenador_compras"]`
* Usuário com `roles = ["user","coordenador_compras"]`
  → `userCanSeeBlock(...) === true`.
* Usuário com `roles = ["user"]`
  → `false` (não tem nenhum dos dois).

---

## 3) RBAC de categorias: `visibleCategories` + `anyRole`

Blocos visíveis são calculados em `apps/host/src/lib/catalog.ts`:

```ts title="visibleBlocks" showLineNumbers
export const visibleBlocks = (catalog: Catalog, user?: User): Block[] => {
  const blocks = catalog?.blocks ?? [];
  return blocks.filter((b) => userCanSeeBlock(user ?? null, b));
};
```

Categorias são filtradas assim:

```ts title="visibleCategories + anyRole" showLineNumbers
const anyRole = (userRoles: string[] = [], required?: string[]): boolean => {
  if (!required || required.length === 0) return true;
  for (const r of required) {
    if (userRoles.includes(r)) return true;
  }
  return false;
};

export const visibleCategories = (catalog: Catalog, user?: User): Category[] => {
  const roles = user?.roles ?? [];
  const cats = catalog?.categories ?? [];
  const vBlocks = new Set(visibleBlocks(catalog, user).map((b) => b.categoryId));

  return cats.filter((c) => {
    const hidden = (c as any).hidden as boolean | undefined;
    const required = (c as any).requiredRoles as string[] | undefined;
    if (hidden) return false;
    if (!anyRole(roles, required)) return false;
    return vBlocks.has(c.id);
  });
};
```

Regras de categoria:

1. **hidden**

   * Se `category.hidden === true`, a categoria nem aparece.
2. **requiredRoles**

   * Aplica o mesmo modelo **ANY-of**:

     * se `requiredRoles` vazio/undefined → qualquer usuário (com acesso a blocos) vê;
     * se definido → basta 1 role bater.
3. **Tem pelo menos um bloco visível**

   * Mesmo se a categoria passar no RBAC,
   * só aparece se existir **ao menos um bloco** daquela categoria em `visibleBlocks`.

Isso evita:

* categorias “mortas” na UI (sem nenhum bloco disponível),
* exibir categorias de áreas que o usuário não tem nenhum permissão prática.

---

## 4) RBAC nas rotas: `<RequireRoles />` e páginas

### 4.1. Guard de rota por bloco

Em `App.tsx`, o Host define um wrapper de rota:

```tsx title="App.tsx — RequireRoles" showLineNumbers
function RequireRoles({
  user,
  block,
  children,
}: {
  user: User | null;
  block: Block;
  children: ReactNode;
}) {
  const allowed = useMemo(() => userCanSeeBlock(user, block), [user, block]);
  if (!allowed) return <Navigate to="/403" replace />;
  return <>{children}</>;
}
```

O padrão nas rotas dinâmicas de blocos é:

* pegar o `block` do catálogo (por `name` ou rota),
* envolver a página em `<RequireRoles user={user} block={block}>`.

Se `userCanSeeBlock` retornar `false`:

* o usuário é redirecionado para `/403` (página “Acesso negado”).

### 4.2. RBAC no Dashboard e na visão de categoria

**Dashboard (`HomeDashboard.tsx`)**:

```tsx title="HomeDashboard.tsx — usando visibleBlocks/visibleCategories" showLineNumbers
const blocksVisiveis = useMemo(
  () => (catalog ? visibleBlocks(catalog, user ?? undefined) : []),
  [catalog, user]
);

const categoriasVisiveis = useMemo(
  () => (catalog ? visibleCategories(catalog, user ?? undefined) : []),
  [catalog, user]
);

// Renderiza cards por categoria, só com blocksVisiveis
```

**Visão de categoria (`CategoryView.tsx`)**:

```tsx title="CategoryView.tsx — filtro por categoria + RBAC" showLineNumbers
const { id } = useParams<{ id: string }>();
const { user } = useAuth();

const category = useMemo(
  () => catalog.categories?.find((c) => c.id === id),
  [catalog, id]
);

const blocks = useMemo(() => {
  return (catalog.blocks || []).filter(
    (b) => b.categoryId === id && userCanSeeBlock(user ?? null, b)
  );
}, [catalog, id, user]);
```

Ou seja:

* já chega para o usuário **só blocos** que ele pode ver;
* se alguém tentar navegar direto para `/categorias/<id>` de uma categoria onde não
  tem permissão de nenhum bloco:

  * a tela aparece vazia (só header e link “Voltar ao início”).

---

## 5) Relação Host × BFF: RBAC de UI vs RBAC de API

No BFF, o RBAC “de verdade” é implementado em `apps/bff/app/auth/rbac.py`:

```py title="require_roles_any no BFF (resumo)" showLineNumbers
def require_roles_any(*roles_required: str):
    """
    Dependência de RBAC: exige ao menos **um** dos papéis informados.

    Regras
    ------
    - `admin` ou `is_superuser=True` têm bypass.
    - Encadeia com `require_password_changed` para reforçar fluxo de segurança.
    """
    required = _norm(roles_required)

    def dep(req: Request) -> Dict[str, Any]:
        user = require_password_changed(req)
        user_roles = _norm(user.get("roles"))
        if user.get("is_superuser") is True or "admin" in user_roles:
            return user
        if not required:
            return user
        if user_roles.isdisjoint(required):
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    return dep
```

Pontos-chave:

* Host e BFF usam o **mesmo modelo conceitual**:

  * ANY-of (`requiredRoles` vs `user.roles`),
  * bypass para `admin` e `is_superuser`.
* O Host serve como **camada de UX**:

  * esconde cards/menus/rotas que o usuário não deveria ver,
  * evita cliques em coisas que de qualquer forma dariam 403.
* O BFF é a **autoridade**:

  * qualquer endpoint sensível deve usar `require_roles_any` ou `require_roles_all`,
  * o Host **nunca** substitui a checagem de backend.

> Regra de ouro:
>
> * **BFF protege dados e ações.**
> * **Host protege UX** (não mostrar o que não pode, mas nunca confiar só nisso).

---

## 6) Diretrizes para catalogar novos blocos (RBAC)

Quando adicionar um bloco no catálogo (`catalog/catalog.dev.json`) ou criar novas
categorias, siga estas recomendações:

1. **Use `requiredRoles` sempre que o bloco não for “para todos”**

   * Ex.: bloco “Controle de Férias”:

     ```json
     {
       "name": "controle_ferias",
       "requiredRoles": ["rh", "coordenador_rh"]
     }
     ```
   * Qualquer usuário com pelo menos um desses roles vê o bloco.

2. **Combine com o RBAC do BFF**

   * Nas rotas da automação (`apps/bff/app/automations/*.py`), use:

     ```py
     from app.auth.rbac import require_roles_any

     router = APIRouter(
         prefix="/api/automations/controle_ferias",
         dependencies=[Depends(require_roles_any("rh", "coordenador_rh"))],
     )
     ```
   * Assim, mesmo que alguém burle o frontend, o backend devolve 403.

3. **Use `superuserOnly` apenas para ferramentas de administração extrema**

   * Ex.: bloco de “debug” interno:

     ```json
     {
       "name": "debug_internal",
       "requiredRoles": [],
       "superuserOnly": true
     }
     ```
   * `admin` **não** enxerga; só `is_superuser=true`.

4. **Categoria-level RBAC (`Category.requiredRoles`)**

   * Use quando a categoria inteira é específica (ex.: “Administração RH”):

     ```json
     {
       "id": "rh_admin",
       "label": "Administração RH",
       "requiredRoles": ["rh_admin", "rh"]
     }
     ```
   * Mesmo assim, o Host só mostra a categoria se houver pelo menos um bloco visível.

5. **Padronize nomes de roles**

   * Sempre minúsculos e sem espaços: `"compras"`, `"pregoeiro"`, `"rh_admin"`.
   * O Host faz `.trim().toLowerCase()` antes de comparar.

---

## 7) Exemplo completo: checando um bloco no Host

```ts title="Exemplo: decision helper de RBAC no Host" showLineNumbers
import type { Block, User } from "@/types";
import { userCanSeeBlock } from "@/types";

/**
 * Decide se o card de um bloco deve ser renderizado.
 */
export function canRenderBlockCard(user: User | null, block: Block): boolean {
  return userCanSeeBlock(user, block);
}
```

Uso na página:

```tsx title="map de blocos com RBAC" showLineNumbers
{blocks.map((block) => {
  if (!canRenderBlockCard(user, block)) return null;
  return (
    <button
      key={block.name}
      className="rounded-xl border border-slate-200 px-4 py-3"
      onClick={() => nav(primaryPathOf(block) ?? "/")}
    >
      <div className="font-semibold text-slate-800">{block.displayName ?? block.name}</div>
      <p className="text-xs text-slate-500 mt-1">{block.description}</p>
    </button>
  );
})}
```

---

> _Criado em 2025-12-01_