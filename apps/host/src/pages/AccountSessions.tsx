// apps/host/src/pages/AccountSessions.tsx
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listSessions, revokeSession, type SessionItem } from "@/lib/api";
import { useAuth } from "@/auth/AuthProvider";

/**
 * Selo visual com variações semânticas (ok/aviso/mutado).
 *
 * @param kind Variação visual do selo.
 * @param children Conteúdo textual do selo.
 */
function Badge({ kind, children }: { kind: "ok" | "warn" | "muted"; children: React.ReactNode }) {
  const cls =
    kind === "ok"
      ? "bg-emerald-100 text-emerald-700 border-emerald-200"
      : kind === "warn"
      ? "bg-amber-100 text-amber-800 border-amber-200"
      : "bg-slate-100 text-slate-700 border-slate-200";
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs ${cls}`}>
      {children}
    </span>
  );
}

/**
 * Formata datas ISO em string local amigável.
 *
 * @param s Data em ISO-8601 ou `null/undefined`.
 * @returns String formatada ou traço quando ausente.
 */
function fmtDate(s?: string | null) {
  if (!s) return "—";
  try {
    const d = new Date(s);
    return d.toLocaleString();
  } catch {
    return s;
  }
}

/**
 * Determina o status computado da sessão.
 *
 * @param s Item de sessão.
 * @returns "active" | "revoked" | "expired".
 */
function statusOf(s: SessionItem): "active" | "revoked" | "expired" {
  if (s.revoked_at) return "revoked";
  if (new Date(s.expires_at).getTime() <= Date.now()) return "expired";
  return "active";
}

/**
 * Página de gerenciamento de sessões da conta.
 *
 * Funcionalidades
 * ---------------
 * - Lista sessões do usuário autenticado.
 * - Permite revogar sessões (incluindo a atual).
 * - Filtro para exibir todas ou apenas ativas.
 */
export default function AccountSessions() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [items, setItems] = useState<SessionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  /**
   * Recarrega a lista de sessões a partir da API.
   */
  const reload = async () => {
    setLoading(true);
    setErr(null);
    try {
      const s = await listSessions();
      setItems(s);
    } catch (e: any) {
      setErr(e?.message || "Falha ao carregar sessões");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void reload();
  }, []);

  /**
   * Conjunto filtrado conforme o toggle "mostrar todas".
   */
  const filtered = useMemo(() => {
    if (showAll) return items;
    return items.filter((x) => statusOf(x) === "active");
  }, [items, showAll]);

  /**
   * Sessão marcada como atual pelo backend.
   */
  const current = useMemo(() => items.find((x) => x.current), [items]);

  /**
   * Revoga uma sessão pelo id. Se for a sessão atual, o usuário é deslogado.
   *
   * @param id Identificador da sessão a revogar.
   */
  const onRevoke = async (id: string) => {
    const isCurrent = current?.id === id;
    const label = isCurrent ? "sua sessão atual" : "esta sessão";
    if (!confirm(`Tem certeza que deseja revogar ${label}?`)) return;
    try {
      setRevokingId(id);
      await revokeSession(id);
      if (isCurrent) {
        await logout();
        nav("/login", { replace: true });
        return;
      }
      await reload();
    } catch (e: any) {
      alert(e?.message || "Falha ao revogar sessão");
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <div className="mx-auto max-w-5xl p-6">
      <div className="mb-6 flex items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Sessões da conta</h1>
          <p className="text-sm text-slate-600">
            Veja onde sua conta está conectada e revogue acessos que não reconhece.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <label className="inline-flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-slate-300"
              checked={showAll}
              onChange={(e) => setShowAll(e.target.checked)}
            />
            Mostrar todas (inclui revogadas/expiradas)
          </label>
          <button
            onClick={() => reload()}
            className="rounded-md border px-3 py-1.5 text-sm hover:bg-slate-50"
            disabled={loading}
            title="Recarregar"
          >
            {loading ? "Carregando…" : "Atualizar"}
          </button>
        </div>
      </div>

      {err && (
        <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          {err}
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50">
            <tr className="text-left">
              <th className="px-4 py-2">Sessão</th>
              <th className="px-4 py-2">Criada</th>
              <th className="px-4 py-2">Último acesso</th>
              <th className="px-4 py-2">Expira</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">IP</th>
              <th className="px-4 py-2">Agente</th>
              <th className="px-4 py-2 text-right">Ações</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-slate-500">
                  {loading ? "Carregando…" : "Nenhuma sessão para exibir."}
                </td>
              </tr>
            )}

            {filtered.map((s) => {
              const st = statusOf(s);
              return (
                <tr key={s.id} className="border-t">
                  <td className="px-4 py-2">
                    <div className="font-mono text-xs break-all">{s.id}</div>
                    {s.current && <div className="mt-0.5 text-[11px] text-sky-700">Sessão atual</div>}
                  </td>
                  <td className="px-4 py-2">{fmtDate(s.created_at)}</td>
                  <td className="px-4 py-2">{fmtDate(s.last_seen_at)}</td>
                  <td className="px-4 py-2">{fmtDate(s.expires_at)}</td>
                  <td className="px-4 py-2">
                    {st === "active" && <Badge kind="ok">Ativa</Badge>}
                    {st === "revoked" && <Badge kind="muted">Revogada</Badge>}
                    {st === "expired" && <Badge kind="warn">Expirada</Badge>}
                  </td>
                  <td className="px-4 py-2">{s.ip ?? "—"}</td>
                  <td className="px-4 py-2">
                    <span className="block max-w-[28ch] truncate" title={s.user_agent ?? ""}>
                      {s.user_agent ?? "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">
                    <button
                      onClick={() => onRevoke(s.id)}
                      disabled={revokingId === s.id || st !== "active"}
                      className={[
                        "rounded-md border px-3 py-1.5 text-xs",
                        st === "active" ? "hover:bg-slate-50" : "cursor-not-allowed opacity-40",
                      ].join(" ")}
                    >
                      {revokingId === s.id ? "Revogando…" : "Revogar"}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-4 text-xs text-slate-500">* Revogar a sessão atual pode encerrar seu acesso imediatamente.</div>
    </div>
  );
}
