import { useEffect, useMemo, useState } from "react";
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
import NotFound from "@/pages/NotFound";
import HomeDashboard from "@/pages/HomeDashboard";

function IframeBlock({ src }: { src: string }) {
  return (
    <iframe
      src={src}
      className="w-full border-0"
      style={{ height: "calc(100vh - var(--header-h))" }}
    />
  );
}

/** Redireciona a raiz (/) para a Home após auth + catálogo */
function RootRedirect({
  user,
  catalog,
}: {
  user: User | null;
  catalog: Catalog | null;
}) {
  if (!user) return <Navigate to="/login" replace />;
  if (!catalog) return <div className="p-6">Carregando catálogo…</div>;
  return <Navigate to="/inicio" replace />;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();
  const loc = useLocation();

  // Autenticação
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

  // Catálogo (após login)
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

  const firstPath = useMemo(() => {
    if (!catalog || !catalog.blocks.length) return "/login";
    const b0 = catalog.blocks[0];
    const nav0 = b0.navigation?.[0]?.path;
    const rt0 = b0.routes?.[0]?.path;
    return nav0 || rt0 || "/login";
  }, [catalog]);

  // Se estiver no /login ou / quando catálogo terminar de carregar, vá para a home
  useEffect(() => {
    if (user && catalog && (loc.pathname === "/login" || loc.pathname === "/")) {
      nav("/inicio", { replace: true });
    }
  }, [user, catalog, loc.pathname, nav]);

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
    await logout();
    setUser(null);
    setCatalog(null);
    nav("/login");
  };

  // Proteção de rota
  if (!loading && !user && loc.pathname !== "/login") {
    return <Navigate to="/login" replace />;
  }

  // UI helpers
  const activeCls = ({ isActive }: { isActive: boolean }) =>
    [
      "px-3 py-1.5 rounded-md text-sm transition",
      isActive
        ? "bg-sky-600 text-white shadow-sm"
        : "text-slate-700 hover:bg-slate-100",
    ].join(" ");

  const initials =
    user?.nome
      ?.split(" ")
      .map((s) => s[0])
      .join("")
      .slice(0, 2)
      .toUpperCase() || "AG";

  return (
    <div className="min-h-full">
      {/* Header */}
      <header
        className="sticky top-0 z-50 w-full border-b bg-white/80 backdrop-blur"
        // define a CSS var usada pelo IframeBlock p/ calcular a altura
        style={{ ["--header-h" as any]: "56px" }}
      >
        <div className="mx-auto max-w-6xl px-4 h-[var(--header-h)] flex items-center gap-4">
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

          {/* Menu do catálogo */}
          {catalog?.blocks?.flatMap((b) => b.navigation || []).map((n) => (
            <NavLink key={n.path} to={n.path} className={activeCls}>
              {n.label}
            </NavLink>
          ))}

          <div className="ml-auto flex items-center gap-3">
            {user && (
              <span className="hidden sm:inline text-sm text-slate-600">
                Olá, {user.nome}
              </span>
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

        {/* Home com cards de blocos */}
        <Route
          path="/inicio"
          element={<HomeDashboard catalog={catalog} firstPath={firstPath} />}
        />

        {/* Raiz decide com base em auth + catálogo */}
        <Route path="/" element={<RootRedirect user={user} catalog={catalog} />} />

        {/* Rotas do catálogo */}
        {catalog?.blocks?.map((b) =>
          b.routes?.map((r) => (
            <Route key={r.path} path={r.path} element={routeElementFor(b, r)} />
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

function LazyLogin() {
  const [Comp, setComp] = useState<null | React.ComponentType>(null);
  useEffect(() => {
    import("@/pages/Login").then((m) => setComp(() => m.default));
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
      <h2 className="text-lg font-semibold">Ping eProtocolo (mock)</h2>
      <pre className="mt-2 text-sm bg-slate-100 p-3 rounded">
        {err ? err : JSON.stringify(resp, null, 2)}
      </pre>
    </div>
  );
}
