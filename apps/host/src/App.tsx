import React, { useEffect, useState } from "react";
import { BrowserRouter, Routes, Route, Link, Navigate } from "react-router-dom";
import { fetchMe, login, logout } from "./auth";
import { loadCatalog } from "./catalog";
import type { Block, User } from "./types";
import IframeBlock from "./IframeBlock";

function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetchMe().then(u => { setUser(u); setLoading(false); })
             .catch(() => setLoading(false));
  }, []);
  return { user, loading };
}

function Shell() {
  const { user, loading } = useAuth();
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const url = (import.meta.env.VITE_CATALOG_URL as string) || "/catalog/dev";
    loadCatalog(url).then(c => setBlocks(c.blocks)).catch(e => setErr(String(e)));
  }, []);

  if (loading) return <div style={{ padding: 16 }}>Carregando…</div>;

  if (!user)
    return (
      <div style={{ padding: 24 }}>
        <h1>Portal AGEPAR</h1>
        <p>Você precisa entrar para usar o portal.</p>
        <button onClick={login}>Entrar</button>
      </div>
    );

  return (
    <div>
      <header style={{ display: "flex", gap: 16, alignItems: "center", padding: 12, borderBottom: "1px solid #eee" }}>
        <strong>Portal AGEPAR</strong>
        <nav style={{ display: "flex", gap: 12 }}>
          {blocks.flatMap(b => b.navigation).map((n, i) => (
            <Link key={i} to={n.path}>{n.label}</Link>
          ))}
        </nav>
        <div style={{ marginLeft: "auto" }}>
          Olá, {user.name} — <button onClick={logout}>Sair</button>
        </div>
      </header>
      <main>
        <Routes>
          {blocks.map(block =>
            block.routes.map(r => (
              <Route key={`${block.name}${r.path}`} path={r.path} element={<IframeBlock url={block.ui.url} />} />
            ))
          )}
          <Route path="/" element={<Navigate to={blocks[0]?.navigation[0]?.path || "/home"} replace />} />
          <Route path="*" element={<div style={{ padding: 24 }}>{err || "Rota não encontrada"}</div>} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
