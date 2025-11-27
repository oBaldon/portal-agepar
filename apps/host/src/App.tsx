// src/App.tsx
/**
 * App principal do Host (SPA)
 *
 * Propósito
 * ---------
 * Orquestra as rotas públicas e autenticadas, aplica guardas de navegação
 * (401/403), carrega o catálogo de automações após login e renderiza blocos
 * do catálogo (iframe ou placeholder React).
 *
 * Regras/Comportamentos
 * ---------------------
 * - Redireciona 401 para /login (com motivo) e 403 para /403.
 * - Páginas públicas com gate: /login e /registrar não montam se já autenticado.
 * - Rota de troca de senha obrigatória: /auth/force-change-password.
 * - Carregamento do catálogo acontece somente quando há usuário logado.
 * - RBAC por bloco utilizando userCanSeeBlock; categorias exibidas apenas se
 *   houver ao menos um bloco visível.
 *
 * Segurança
 * ---------
 * - Handlers globais de API encerram a sessão no cliente quando necessário.
 * - Rotas privadas exigem sessão válida; caso contrário, redirecionam ao /login.
 *
 * Referências
 * -----------
 * - React Router v6 (Routes, Route, Navigate, NavLink).
 * - API do BFF: configureApiHandlers, pingEProtocolo.
 * - Catálogo: loadCatalog(), tipos Catalog/Block/BlockRoute.
 * - RBAC: userCanSeeBlock.
 */

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

function AuthPageGate({ user, children }: { user: User | null; children: ReactNode }) {
  if (user) return <Navigate to="/inicio" replace />;
  return <>{children}</>;
}

function IframeBlock({ src }: { src: string }) {
  return (
    <iframe
      src={src}
      className="w-full border-0"
      style={{ height: "calc(100vh - var(--header-h))" }}
    />
  );
}

function RootRedirect({ user, catalog }: { user: User | null; catalog: Catalog | null }) {
  if (!user) return <Navigate to="/login" replace />;
  if (!catalog) return <div className="p-6">Carregando catálogo…</div>;
  return <Navigate to="/inicio" replace />;
}

export default function App() {
  const { user, loading, logout: doLogout } = useAuth();
  const [catalog, setCatalog] = useState<Catalog | null>(null);

  const nav = useNavigate();
  const loc = useLocation();
  const isPublicPath = (p: string) => p === "/login" || p === "/registrar" || p === "/403";

  useEffect(() => {
    configureApiHandlers({
      onUnauthorized: () => {
        if (user) void doLogout();
        if (!isPublicPath(loc.pathname)) {
          nav("/login?reason=session_expired", { replace: true });
        }
      },
      onForbidden: () => {
        nav("/403", { replace: true });
      },
    });
  }, [doLogout, nav, loc.pathname, user]);

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

  const onLogout = async () => {
    await doLogout();
    setCatalog(null);
    nav("/login");
  };

  const publicPaths = new Set<string>(["/login", "/registrar", "/403"]);
  if (!loading && !user && !publicPaths.has(loc.pathname)) {
    return <Navigate to="/login" replace />;
  }

  const activeCls = ({ isActive }: { isActive: boolean }) =>
    [
      "px-3 py-1.5 rounded-md text-sm transition",
      isActive ? "bg-sky-600 text-white shadow-sm" : "text-slate-700 hover:bg-slate-100",
    ].join(" ");

  const initials =
    user?.nome?.split(" ").map((s) => s[0]).join("").slice(0, 2).toUpperCase() || "AG";

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
      <header
        className="sticky top-0 z-50 w-full border-b bg-white/80 backdrop-blur"
        style={{ ["--header-h" as any]: "56px" }}
      >
        <div className="mx-auto max-w-6xl px-4 h-[var(--header-h)] flex items-center gap-4">
          <Link to={user ? "/inicio" : "/"} className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-xl bg-sky-600 text-white grid place-items-center font-semibold">
              A
            </div>
            <div className="font-semibold tracking-tight">
              Plataforma <span className="text-sky-700">AGEPAR</span>
            </div>
          </Link>

          {user && (
            <>
              <NavLink to="/inicio" className={activeCls}>
                Início
              </NavLink>
              {visibleCategories.map((cat) => (
                <NavLink key={cat.id} to={`/categoria/${cat.id}`} className={activeCls}>
                  {cat.label}
                </NavLink>
              ))}
            </>
          )}

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

      <Routes>
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

        <Route path="/auth/force-change-password" element={<LazyForceChangePassword />} />

        <Route path="/inicio" element={<HomeDashboard catalog={catalog} user={user} />} />

        <Route path="/categoria/:id" element={<CategoryView catalog={catalog} />} />

        <Route path="/" element={<RootRedirect user={user} catalog={catalog} />} />

        <Route path="/conta/sessoes" element={<AccountSessions />} />

        {(catalog?.blocks ?? [])
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

        <Route path="/__ping" element={<PingView />} />

        <Route path="*" element={<NotFound />} />
      </Routes>
    </div>
  );
}

function LazyLogin() {
  const [Comp, setComp] = useState<null | React.ComponentType>(null);
  useEffect(() => {
    import("@/pages/Login").then((m) => setComp(() => m.default));
  }, []);
  return Comp ? <Comp /> : <div className="p-6">Carregando…</div>;
}

function LazyRegister() {
  const [Comp, setComp] = useState<null | React.ComponentType>(null);
  useEffect(() => {
    import("@/pages/Register").then((m) => setComp(() => m.default));
  }, []);
  return Comp ? <Comp /> : <div className="p-6">Carregando…</div>;
}

function LazyRegisterDisabled() {
  const [Comp, setComp] = useState<null | React.ComponentType>(null);
  useEffect(() => {
    import("@/pages/RegisterDisabled").then((m) => setComp(() => m.default));
  }, []);
  return Comp ? <Comp /> : <div className="p-6">Carregando…</div>;
}

function LazyForceChangePassword() {
  const [Comp, setComp] = useState<null | React.ComponentType>(null);
  useEffect(() => {
    import("@/pages/ForceChangePassword").then((m) => setComp(() => m.default));
  }, []);
  return Comp ? <Comp /> : <div className="p-6">Carregando…</div>;
}

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
