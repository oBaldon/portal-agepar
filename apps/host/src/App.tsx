// src/App.tsx
import { useEffect, useState } from "react";
import {
  Link,
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router-dom";

import { getMe, logout, pingEProtocolo } from "@/lib/api";
import { loadCatalog } from "@/lib/catalog";

import type { Catalog, Block, BlockRoute, User } from "@/types";
import { userCanSeeBlock } from "@/types"; // para filtrar categorias “vazias” para o usuário

import NotFound from "@/pages/NotFound";
import HomeDashboard from "@/pages/HomeDashboard";
import CategoryView from "@/pages/CategoryView";

/* ============================================================================
 * Componente utilitário para <iframe/> com altura ajustada ao header
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
  const [user, setUser] = useState<User | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loading, setLoading] = useState(true);

  const nav = useNavigate();
  const loc = useLocation();

  // ---------------------------
  // 1) Autenticação (getMe)
  // ---------------------------
  useEffect(() => {
    (async () => {
      try {
        const me = await getMe();
        setUser(me);
      } catch {
        setUser(null);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // -----------------------------------------
  // 2) Carrega catálogo após autenticação
  // -----------------------------------------
  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const c = await loadCatalog();
        setCatalog(c);
      } catch (e) {
        console.error("Falha ao carregar catálogo", e);
      }
    })();
  }, [user]);

  // -------------------------------------------------------------
  // 3) Se estiver no /login ou / quando catálogo terminar de
  //    carregar, vá para a home (/inicio)
  // -------------------------------------------------------------
  useEffect(() => {
    if (user && catalog && (loc.pathname === "/login" || loc.pathname === "/")) {
      nav("/inicio", { replace: true });
    }
  }, [user, catalog, loc.pathname, nav]);

  // ----------------------------------------
  // 4) Resolve elemento de rota por bloco
  // ----------------------------------------
  const routeElementFor = (block: Block, r: BlockRoute) => {
    if (r.kind === "iframe" && block.ui.type === "iframe") {
      return <IframeBlock src={block.ui.url} />;
    }
    if (r.kind === "react") {
      // Suporte futuro: registrar componentes React nativos no host
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

  // -------------------------
  // 5) Logout
  // -------------------------
  const onLogout = async () => {
    await logout();
    setUser(null);
    setCatalog(null);
    nav("/login");
  };

  // ------------------------------------------------------------
  // 6) Proteção de rota: se não está logado (e não é /login)
  // ------------------------------------------------------------
  if (!loading && !user && loc.pathname !== "/login") {
    return <Navigate to="/login" replace />;
  }

  // ------------------------------------------------------------
  // 7) Helpers de UI (Navbar)
  // ------------------------------------------------------------
  const activeCls = ({ isActive }: { isActive: boolean }) =>
    [
      "px-3 py-1.5 rounded-md text-sm transition",
      isActive ? "bg-sky-600 text-white shadow-sm" : "text-slate-700 hover:bg-slate-100",
    ].join(" ");

  const initials =
    user?.nome?.split(" ").map((s) => s[0]).join("").slice(0, 2).toUpperCase() || "AG";

  // Mostra apenas categorias que têm ao menos um bloco visível ao usuário
  const visibleCategories = (catalog?.categories ?? []).filter((cat) =>
    (catalog?.blocks ?? []).some(
      (b) => b.categoryId === cat.id && !b.hidden && userCanSeeBlock(user, b)
    )
  );

  return (
    <div className="min-h-full">
      {/* Header */}
      <header
        className="sticky top-0 z-50 w-full border-b bg-white/80 backdrop-blur"
        // define a CSS var usada pelo IframeBlock p/ calcular a altura
        style={{ ["--header-h" as any]: "56px" }}
      >
        <div className="mx-auto max-w-6xl px-4 h-[var(--header-h)] flex items-center gap-4">
          {/* Logo + link para a Home */}
          <Link to="/inicio" className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-xl bg-sky-600 text-white grid place-items-center font-semibold">
              A
            </div>
            <div className="font-semibold tracking-tight">
              Portal <span className="text-sky-700">AGEPAR</span>
            </div>
          </Link>

          {/* “Início” sempre visível */}
          <NavLink to="/inicio" className={activeCls}>
            Início
          </NavLink>

          {/* Navbar por CATEGORIAS (não por blocos) */}
          {visibleCategories.map((cat) => (
            <NavLink key={cat.id} to={`/categoria/${cat.id}`} className={activeCls}>
              {cat.label}
            </NavLink>
          ))}

          {/* Ações e usuário */}
          <div className="ml-auto flex items-center gap-3">
            {user && (
              <span className="hidden sm:inline text-sm text-slate-600">Olá, {user.nome}</span>
            )}
            {user && (
              <div className="h-8 w-8 rounded-full bg-slate-200 grid place-items-center text-xs font-semibold text-slate-700">
                {initials}
              </div>
            )}
            {user && (
              <button
                onClick={onLogout}
                className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50"
              >
                Sair
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Rotas */}
      <Routes>
        {/* Login */}
        <Route path="/login" element={<LazyLogin />} />

        {/* Home com cards agrupados por categorias (RBAC aplicado no componente) */}
        <Route path="/inicio" element={<HomeDashboard catalog={catalog} user={user} />} />

        {/* Página de listagem por categoria */}
        <Route path="/categoria/:id" element={<CategoryView catalog={catalog} />} />

        {/* Raiz decide com base em auth + catálogo */}
        <Route path="/" element={<RootRedirect user={user} catalog={catalog} />} />

        {/* Rotas dos blocos do catálogo (iframe/react) */}
        {catalog?.blocks?.map((b) =>
          b.routes?.map((r) => (
            <Route key={`${b.name}:${r.path}`} path={r.path} element={routeElementFor(b, r)} />
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
      <h2 className="text-lg font-semibold">Ping eProtocolo (mock)</h2>
      <pre className="mt-2 text-sm bg-slate-100 p-3 rounded">
        {err ? err : JSON.stringify(resp, null, 2)}
      </pre>
    </div>
  );
}
