// apps/host/src/pages/Notifications.tsx
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/api";
import type { Notification } from "@/types";

const NOTIF_EVENT = "portal:notifications:unread";
function emitUnread(unread: number) {
  window.dispatchEvent(new CustomEvent(NOTIF_EVENT, { detail: { unread } }));
}

function fmt(dt: string): string {
  try {
    return new Date(dt).toLocaleString("pt-BR");
  } catch {
    return dt;
  }
}

export default function NotificationsPage() {
  const nav = useNavigate();
  const { user } = useAuth();

  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState<boolean>(false);

  const unreadCount = useMemo(
    () => items.filter((n) => !n.readAt).length,
    [items]
  );

  function markReadOptimistic(id: string) {
    setItems((prev) => {
      const now = new Date().toISOString();
      const target = prev.find((n) => n.id === id);
      if (!target || target.readAt) return prev;

      // Se estiver filtrando somente não lidas, ao marcar como lida deve SUMIR da lista imediatamente.
      if (unreadOnly) {
        const next = prev.filter((n) => n.id !== id);
        emitUnread(next.length); // em modo unreadOnly, o total de não lidas = tamanho da lista
        return next;
      }

      const next = prev.map((n) => (n.id === id ? { ...n, readAt: now } : n));
      emitUnread(next.filter((n) => !n.readAt).length);
      return next;
    });
  }

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listNotifications({ unreadOnly, limit: 200, offset: 0 });
      setItems(data);
      // Mantém o sino sincronizado imediatamente ao carregar a página.
      const unread = unreadOnly ? data.length : data.filter((n) => !n.readAt).length;
      emitUnread(unread);
    } catch (e: any) {
      const status = Number(e?.status || 0);
      const detail =
        e?.data?.detail ||
        (typeof e?.data === "string" ? e.data : null) ||
        (status ? `Erro (${status})` : "Erro ao carregar notificações");

      setError(String(detail));
      if (status === 401) nav("/login?reason=401");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!user) return;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id, unreadOnly]);

  async function onMarkRead(id: string) {
    try {
      // otimista: atualiza UI e sino primeiro
      markReadOptimistic(id);
      await markNotificationRead(id);
    } catch (e) {
      console.error(e);
    }
  }

  function onOpenNotification(n: Notification) {
    // Ao abrir, também marca como lida e atualiza o sino imediatamente,
    // sem depender do setState (porque vamos navegar em seguida).
    if (!n.readAt) {
      emitUnread(Math.max(0, unreadCount - 1));
      markReadOptimistic(n.id);
      void markNotificationRead(n.id);
    }
    if (n.actionUrl) nav(n.actionUrl);
  }

  async function onMarkAll() {
    try {
      await markAllNotificationsRead();
      setItems((prev) => {
        const now = new Date().toISOString();
        if (unreadOnly) {
          emitUnread(0);
          return [];
        }
        const next = prev.map((n) => ({ ...n, readAt: n.readAt || now }));
        emitUnread(0);
        return next;
      });
    } catch (e) {
      console.error(e);
    }
  }

  if (!user) {
    return (
      <div className="max-w-4xl mx-auto p-6">
        <h1 className="text-xl font-semibold">Notificações</h1>
        <p className="text-sm text-slate-600 mt-2">
          Você precisa estar autenticado para acessar esta página.
        </p>
        <Link to="/login" className="inline-block mt-4 text-sm underline">
          Ir para login
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Notificações</h1>
          <p className="text-sm text-slate-600 mt-1">
            Caixa de entrada vinculada à sua conta e aos seus cargos (roles).
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setUnreadOnly((v) => !v)}
            className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50"
            title="Filtrar somente não lidas"
          >
            {unreadOnly ? "Mostrando: não lidas" : "Mostrando: todas"}
          </button>

          <button
            onClick={onMarkAll}
            className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50 disabled:opacity-50"
            disabled={unreadCount === 0}
            title="Marcar todas como lidas"
          >
            Marcar tudo como lido
          </button>

          <button
            onClick={load}
            className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50"
            title="Recarregar"
          >
            Recarregar
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-4 border border-rose-200 bg-rose-50 text-rose-900 rounded-md p-3 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="mt-6 text-sm text-slate-600">Carregando…</div>
      ) : items.length === 0 ? (
        <div className="mt-6 text-sm text-slate-600">Nenhuma notificação.</div>
      ) : (
        <div className="mt-6 space-y-3">
          {items.map((n) => {
            const unread = !n.readAt;
            return (
              <div
                key={n.id}
                className={[
                  "border rounded-xl p-4",
                  unread ? "bg-white" : "bg-slate-50",
                ].join(" ")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h2 className="font-medium truncate">{n.title}</h2>
                      {unread && (
                        <span className="text-[11px] px-2 py-0.5 rounded-full border bg-amber-50">
                          Nova
                        </span>
                      )}
                      <span className="text-[11px] px-2 py-0.5 rounded-full border bg-slate-50">
                        {n.level}
                      </span>
                    </div>
                    <div className="text-xs text-slate-500 mt-1">
                      {fmt(n.createdAt)}
                      {n.readAt ? ` • lida em ${fmt(n.readAt)}` : ""}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {n.actionUrl && (
                      <button
                        type="button"
                        className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50"
                        title="Abrir destino"
                        onClick={() => onOpenNotification(n)}
                      >
                        Abrir
                      </button>
                    )}
                    {unread && (
                      <button
                        onClick={() => onMarkRead(n.id)}
                        className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50"
                        title="Marcar como lida"
                      >
                        Marcar lida
                      </button>
                    )}
                  </div>
                </div>

                <div className="text-sm text-slate-700 mt-3 whitespace-pre-wrap">
                  {n.message}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
