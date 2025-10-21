// src/App.tsx
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";

import { configureApiHandlers, pingEProtocolo } from "@/lib/api";
import { loadCatalog } from "@/lib/catalog";

import type { Catalog, Block, BlockRoute, User } from "@/types";
import { userCanSeeBlock } from "@/types";

import NotFound from "@/pages/NotFound";
import HomeDashboard from "@/pages/HomeDashboard";
import CategoryView from "@/pages/CategoryView";
import AccountSessions from "@/pages/AccountSessions";
import Forbidden from "@/pages/Forbidden";
import { useAuth } from "@/auth/AuthProvider";

const ENABLE_SELF_REGISTER = import.meta.env.VITE_ENABLE_SELF_REGISTER === "true";

/* ---------------------------------------------------------------------------
 * Ícones de categorias
 * -------------------------------------------------------------------------*/
// import * as Icons from "lucide-react";
// function CatIcon({ name, className }: { name?: string; className?: string }) {
//   const Ico = name ? (Icons as any)[name] : null;
//   return Ico ? <Ico className={className} aria-hidden="true" /> : null;
// }

/* ============================================================================
 * Guard RBAC de rotas dos blocos
 * ==========================================================================*/
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

/* ============================================================================
 * Gate para páginas públicas (login/registrar) quando já autenticado
 * ==========================================================================*/
function AuthPageGate({ user, children }: { user: User | null; children: ReactNode }) {
  if (user) return <Navigate to="/inicio" replace />;
  return <>{children}</>;
}

/* ============================================================================
 * IframeBlock — altura compensando o header
 * ==========================================================================*/
function IframeBlock({ src }: { src: string }) {
  return (
    <iframe
      src={src}
      className="w-full border-0"
      style={{ height: "calc(100vh - var(--header-h))" }}
    />
  );
}

/* ============================================================================
 * Redireciona a raiz (/) para a Home após auth + catálogo carregados
 * ==========================================================================*/
function RootRedirect({ user, catalog }: { user: User | null; catalog: Catalog | null }) {
  if (!user) return <Navigate to="/login" replace />;
  if (!catalog) return <div className="p-6">Carregando catálogo…</div>;
  return <Navigate to="/inicio" replace />;
}

/* ============================================================================
 * App principal
 * ==========================================================================*/
export default function App() {
  const { user, loading, logout: doLogout } = useAuth();
  const [catalog, setCatalog] = useState<Catalog | null>(null);

  const nav = useNavigate();
  const loc = useLocation();
  // Rotas públicas (não devem redirecionar em 401)
  const isPublicPath = (p: string) => p === "/login" || p === "/registrar" || p === "/403";

  // Interceptadores globais: 401/403
  useEffect(() => {
    configureApiHandlers({
      onUnauthorized: () => {
        // Só tenta encerrar sessão se havia usuário autenticado
        if (user) void doLogout();
        // Não redireciona se já estiver em rota pública (ex.: /registrar)
        if (!isPublicPath(loc.pathname)) {
          nav("/login?reason=session_expired", { replace: true });
        }
      },
      onForbidden: () => {
        nav("/403", { replace: true });
      },
    });
  }, [doLogout,  nav, loc.pathname, user]);

  // Carrega catálogo após autenticação
  useEffect(() => {
    if (!user) {
      setCatalog(null);
      return;
    }
    (async () => {
      try {
        const c = await loadCatalog();
        setCatalog(c);
      } catch (e) {
        console.error("Falha ao carregar catálogo", e);
      }
    })();
  }, [user]);

  // Resolve elemento de rota por bloco
  const routeElementFor = (block: Block, r: BlockRoute) => {
    if (r.kind === "iframe" && block.ui.type === "iframe") {
      return <IframeBlock src={block.ui.url} />;
    }
    if (r.kind === "react") {
      return (
        <div className="p-6">
          <h2 className="text-lg font-semibold">Bloco React não implementado</h2>
          <p className="text-slate-600 mt-2">
            Este host não possui um componente registrado para o bloco{" "}
            <code>{block.name}</code>. Use <code>ui.type: "iframe"</code> no
            catálogo para renderizar via BFF, ou registre o componente no host.
          </p>
        </div>
      );
    }
    return <NotFound />;
  };

  // Logout (via AuthProvider)
  const onLogout = async () => {
    await doLogout();
    setCatalog(null);
    nav("/login");
  };

  // Proteção de rota: permite /login, /registrar e /403 sem auth
  const publicPaths = new Set<string>(["/login", "/registrar", "/403"]);
  if (!loading && !user && !publicPaths.has(loc.pathname)) {
    return <Navigate to="/login" replace />;
  }

  // Helpers de UI (Navbar)
  const activeCls = ({ isActive }: { isActive: boolean }) =>
    [
      "px-3 py-1.5 rounded-md text-sm transition",
      isActive ? "bg-sky-600 text-white shadow-sm" : "text-slate-700 hover:bg-slate-100",
    ].join(" ");

  const initials =
    user?.nome?.split(" ").map((s) => s[0]).join("").slice(0, 2).toUpperCase() || "AG";

  // Mostra apenas categorias visíveis:
  // - categoria NÃO hidden
  // - RBAC ANY-of em category.requiredRoles (se houver)
  // - pelo menos 1 bloco visível (não hidden + userCanSeeBlock)
  const visibleCategories = useMemo(() => {
    const cats = catalog?.categories ?? [];
    const blocks = catalog?.blocks ?? [];
    const roles = user?.roles ?? [];

    const blockIsVisible = (b: any) => {
      if (b?.hidden) return false;
      return userCanSeeBlock(user, b);
    };
    const catHasVisibleBlock = new Set(
      blocks.filter(blockIsVisible).map((b) => b.categoryId)
    );

    const anyRole = (required?: string[]) =>
      !required || required.length === 0 || required.some((r) => roles.includes(r));

    return cats.filter((c: any) => {
      if (c?.hidden) return false;
      if (!anyRole(c?.requiredRoles)) return false;
      return catHasVisibleBlock.has(c.id);
    });
  }, [catalog, user]);

  return (
    <div className="min-h-full">
      {/* Header */}
      <header
        className="sticky top-0 z-50 w-full border-b bg-white/80 backdrop-blur"
        style={{ ["--header-h" as any]: "56px" }}
      >
        <div className="mx-auto max-w-6xl px-4 h-[var(--header-h)] flex items-center gap-4">
          {/* Logo + link para a Home (se logado) ou raiz */}
          <Link to={user ? "/inicio" : "/"} className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-xl bg-sky-600 text-white grid place-items-center font-semibold">
              A
            </div>
            <div className="font-semibold tracking-tight">
              Plataforma <span className="text-sky-700">AGEPAR</span>
            </div>
          </Link>

          {/* “Início” + categorias: apenas quando logado */}
          {user && (
            <>
              <NavLink to="/inicio" className={activeCls}>
                Início
              </NavLink>
              {visibleCategories.map((cat) => (
                <NavLink key={cat.id} to={`/categoria/${cat.id}`} className={activeCls}>
                  {/* Quando icon com lucide-react, descomente o bloco abaixo
                  <span className="inline-flex items-center gap-1.5">
                    <CatIcon name={cat.icon} className="h-4 w-4" />
                    {cat.label}
                  </span>
                  */}
                  {cat.label}
                </NavLink>
              ))}
            </>
          )}

          {/* Ações e usuário */}
          <div className="ml-auto flex items-center gap-3">
            {user ? (
              <>
                <span className="hidden sm:inline text-sm text-slate-600">Olá, {user.nome}</span>
                <div className="h-8 w-8 rounded-full bg-slate-200 grid place-items-center text-xs font-semibold text-slate-700">
                  {initials}
                </div>
                <Link
                  to="/conta/sessoes"
                  className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50"
                  title="Gerenciar sessões ativas"
                >
                  Sessões
                </Link>
                <button
                  onClick={onLogout}
                  className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50"
                >
                  Sair
                </button>
              </>
            ) : (
              <>
                <NavLink to="/login" className={activeCls}>
                  Entrar
                </NavLink>
                {ENABLE_SELF_REGISTER && (
                  <Link
                    to="/registrar"
                    className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50"
                  >
                    Criar conta
                  </Link>
                )}
              </>
            )}
          </div>
        </div>
      </header>

      {/* Rotas */}
      <Routes>
        {/* Públicas com gate: não monta se já estiver logado */}
        <Route
          path="/login"
          element={
            <AuthPageGate user={user}>
              <LazyLogin />
            </AuthPageGate>
          }
        />
        <Route
          path="/registrar"
          element={
            <AuthPageGate user={user}>
              {ENABLE_SELF_REGISTER ? <LazyRegister /> : <LazyRegisterDisabled />}
            </AuthPageGate>
          }
        />
        <Route path="/403" element={<Forbidden />} />

        {/* Home com cards agrupados por categorias */}
        <Route path="/inicio" element={<HomeDashboard catalog={catalog} user={user} />} />

        {/* Página de listagem por categoria */}
        <Route path="/categoria/:id" element={<CategoryView catalog={catalog} />} />

        {/* Raiz decide com base em auth + catálogo */}
        <Route path="/" element={<RootRedirect user={user} catalog={catalog} />} />

        {/* Página de sessões da conta */}
        <Route path="/conta/sessoes" element={<AccountSessions />} />

        {/* Rotas dos blocos do catálogo (com guard RBAC) */}
        {(catalog?.blocks ?? [])
          // não monta rotas de blocos explicitamente escondidos
          .filter((b: any) => !b?.hidden)
          .map((b) =>
            b.routes?.map((r) => (
              <Route
                key={`${b.name}:${r.path}`}
                path={r.path}
                element={
                  <RequireRoles user={user} block={b}>
                    {routeElementFor(b, r)}
                  </RequireRoles>
                }
              />
            ))
          )}

        {/* Ping (smoke) — opcional visualizar em /__ping */}
        <Route path="/__ping" element={<PingView />} />

        {/* Fallback */}
        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

/* ============================================================================
 * Lazy loader do Login (mantém o bundle inicial pequeno)
 * ==========================================================================*/
function LazyLogin() {
  const [Comp, setComp] = useState<null | React.ComponentType>(null);
  useEffect(() => {
    import("@/pages/Login").then((m) => setComp(() => m.default));
  }, []);
  return Comp ? <Comp /> : <div className="p-6">Carregando…</div>;
}

/* ============================================================================
 * Lazy loader do Register
 * ==========================================================================*/
function LazyRegister() {
  const [Comp, setComp] = useState<null | React.ComponentType>(null);
  useEffect(() => {
    import("@/pages/Register").then((m) => setComp(() => m.default));
  }, []);
  return Comp ? <Comp /> : <div className="p-6">Carregando…</div>;
}

/* ============================================================================
 * Lazy loader do RegisterDisabled (aviso quando auto-registro está desativado)
 * ==========================================================================*/
function LazyRegisterDisabled() {
  const [Comp, setComp] = useState<null | React.ComponentType>(null);
  useEffect(() => {
    import("@/pages/RegisterDisabled").then((m) => setComp(() => m.default));
  }, []);
  return Comp ? <Comp /> : <div className="p-6">Carregando…</div>;
}

/* ============================================================================
 * PingView — utilitário para testar conectividade com o BFF
 * ==========================================================================*/
function PingView() {
  const [resp, setResp] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    (async () => {
      try {
        setResp(await pingEProtocolo());
      } catch (e: any) {
        setErr(e?.message || "erro");
      }
    })();
  }, []);
  return (
    <div className="p-6">
      <h2 className="text-lg font-semibold">Ping eProtocolo</h2>
      <pre className="mt-2 text-sm bg-slate-100 p-3 rounded">
        {err ? err : JSON.stringify(resp, null, 2)}
      </pre>
    </div>
  );
}
