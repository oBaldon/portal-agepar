// apps/host/src/pages/Notifications.tsx
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import {
  deleteNotification,
  deleteReadNotifications,
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

function levelClasses(level: Notification["level"]): string {
  switch (level) {
    case "success":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "warning":
      return "border-amber-200 bg-amber-50 text-amber-700";
    case "danger":
      return "border-rose-200 bg-rose-50 text-rose-700";
    default:
      return "border-slate-200 bg-slate-50 text-slate-700";
  }
}

export default function NotificationsPage() {
  const nav = useNavigate();
  const { user } = useAuth();

  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [unreadOnly, setUnreadOnly] = useState<boolean>(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [bulkBusy, setBulkBusy] = useState<boolean>(false);

  const unreadCount = useMemo(
    () => items.filter((n) => !n.readAt).length,
    [items]
  );
  const readCount = useMemo(
    () => items.filter((n) => !!n.readAt).length,
    [items]
  );

  function syncUnreadFrom(next: Notification[]) {
    const unread = unreadOnly ? next.length : next.filter((n) => !n.readAt).length;
    emitUnread(unread);
  }

  function markReadOptimistic(id: string) {
    setItems((prev) => {
      const now = new Date().toISOString();
      const target = prev.find((n) => n.id === id);
      if (!target || target.readAt) return prev;

      if (unreadOnly) {
        const next = prev.filter((n) => n.id !== id);
        syncUnreadFrom(next);
        return next;
      }

      const next = prev.map((n) => (n.id === id ? { ...n, readAt: now } : n));
      syncUnreadFrom(next);
      return next;
    });
  }

  function deleteOptimistic(id: string) {
    setItems((prev) => {
      const next = prev.filter((n) => n.id !== id);
      syncUnreadFrom(next);
      return next;
    });
  }

  function deleteReadOptimistic() {
    setItems((prev) => {
      const next = prev.filter((n) => !n.readAt);
      syncUnreadFrom(next);
      return next;
    });
  }

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await listNotifications({ unreadOnly, limit: 200, offset: 0 });
      setItems(data);
      syncUnreadFrom(data);
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
      setBusyId(id);
      markReadOptimistic(id);
      await markNotificationRead(id);
    } catch (e) {
      console.error(e);
      await load();
    } finally {
      setBusyId(null);
    }
  }

  async function onDelete(id: string) {
    try {
      setBusyId(id);
      deleteOptimistic(id);
      await deleteNotification(id);
    } catch (e) {
      console.error(e);
      await load();
    } finally {
      setBusyId(null);
    }
  }

  function onOpenNotification(n: Notification) {
    if (!n.readAt) {
      emitUnread(Math.max(0, unreadCount - 1));
      markReadOptimistic(n.id);
      void markNotificationRead(n.id);
    }
    if (n.actionUrl) nav(n.actionUrl);
  }

  async function onMarkAll() {
    try {
      setBulkBusy(true);
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
      await load();
    } finally {
      setBulkBusy(false);
    }
  }

  async function onDeleteRead() {
    try {
      setBulkBusy(true);
      deleteReadOptimistic();
      await deleteReadNotifications();
    } catch (e) {
      console.error(e);
      await load();
    } finally {
      setBulkBusy(false);
    }
  }

  if (!user) {
    return (
      <div className="max-w-5xl mx-auto p-6">
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
    <div className="max-w-5xl mx-auto p-6">
      <div className="border rounded-2xl bg-white shadow-sm p-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-xl font-semibold">Notificações</h1>
            <p className="text-sm text-slate-600 mt-1">
              Caixa de entrada vinculada à sua conta e aos seus cargos.
            </p>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={() => setUnreadOnly((v) => !v)}
              className={[
                "text-sm rounded-md px-3 py-1.5 border",
                unreadOnly
                  ? "bg-slate-900 text-white border-slate-900"
                  : "bg-white hover:bg-slate-50 border-slate-300 text-slate-700",
              ].join(" ")}
              title="Alternar filtro"
            >
              {unreadOnly ? "Mostrando: não lidas" : "Mostrando: todas"}
            </button>

            <button
              onClick={onMarkAll}
              className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50 disabled:opacity-50"
              disabled={unreadCount === 0 || bulkBusy}
              title="Marcar todas como lidas"
            >
              Marcar tudo como lido
            </button>

            <button
              onClick={onDeleteRead}
              className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50 disabled:opacity-50"
              disabled={readCount === 0 || bulkBusy}
              title="Apagar notificações já lidas"
            >
              Apagar lidas
            </button>

            <button
              onClick={load}
              className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50"
              title="Recarregar"
              disabled={bulkBusy}
            >
              Recarregar
            </button>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-2 flex-wrap">
          <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600">
            Total: {items.length}
          </span>
          <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs text-amber-700">
            Não lidas: {unreadCount}
          </span>
          <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-100 px-3 py-1 text-xs text-slate-600">
            Lidas: {readCount}
          </span>
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
        <div className="mt-6 border rounded-2xl bg-white p-8 text-sm text-slate-600 text-center">
          Nenhuma notificação.
        </div>
      ) : (
        <div className="mt-6 space-y-3">
          {items.map((n) => {
            const unread = !n.readAt;
            const isBusy = busyId === n.id;

            return (
              <div
                key={n.id}
                className={[
                  "border rounded-2xl p-4 transition-colors",
                  unread
                    ? "bg-white border-slate-200 shadow-sm"
                    : "bg-slate-100/90 border-slate-200 opacity-80",
                ].join(" ")}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <h2 className="font-medium truncate">{n.title}</h2>

                      <span
                        className={[
                          "text-[11px] px-2 py-0.5 rounded-full border",
                          unread
                            ? "border-amber-200 bg-amber-50 text-amber-700"
                            : "border-slate-200 bg-slate-200/70 text-slate-600",
                        ].join(" ")}
                      >
                        {unread ? "Não lida" : "Lida"}
                      </span>

                      <span
                        className={[
                          "text-[11px] px-2 py-0.5 rounded-full border",
                          levelClasses(n.level),
                        ].join(" ")}
                      >
                        {n.level}
                      </span>
                    </div>

                    <div className="text-xs text-slate-500 mt-1">
                      {fmt(n.createdAt)}
                      {n.readAt ? ` • lida em ${fmt(n.readAt)}` : ""}
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
                    {n.actionUrl && (
                      <button
                        type="button"
                        className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50"
                        title="Abrir destino"
                        onClick={() => onOpenNotification(n)}
                        disabled={isBusy}
                      >
                        Abrir
                      </button>
                    )}

                    {unread && (
                      <button
                        onClick={() => onMarkRead(n.id)}
                        className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50 disabled:opacity-50"
                        title="Marcar como lida"
                        disabled={isBusy}
                      >
                        Marcar lida
                      </button>
                    )}

                    <button
                      onClick={() => onDelete(n.id)}
                      className="text-sm border rounded-md px-3 py-1.5 hover:bg-slate-50 text-rose-700 border-rose-200 disabled:opacity-50"
                      title="Apagar notificação"
                      disabled={isBusy}
                    >
                      Apagar
                    </button>
                  </div>
                </div>

                <div
                  className={[
                    "text-sm mt-3 whitespace-pre-wrap",
                    unread ? "text-slate-700" : "text-slate-500",
                  ].join(" ")}
                >
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
