import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { PlatformAlertItem } from "@/types";
import {
  confirmPendingAlert,
  getPendingAlerts,
  markPendingAlertSeen,
  objectPendingAlert,
} from "@/lib/api";

const SYNC_STORAGE_KEY = "portal:avisos:sync";
const DISMISS_STORAGE_KEY = "portal:avisos:dismissed-until";
const BROADCAST_CHANNEL_NAME = "portal-agepar-avisos";
const DEFAULT_TAB_TITLE = document.title.replace(/^\(\d+\)\s*/, "");

type Props = {
  enabled: boolean;
  pathname: string;
};

type DismissMap = Record<string, number>;

function isDismissed(map: DismissMap, alertId: string): boolean {
  const until = map[alertId] ?? 0;
  return until > Date.now();
}

function loadDismissMap(): DismissMap {
  try {
    const raw = window.sessionStorage.getItem(DISMISS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(([, value]) => typeof value === "number" && Number.isFinite(value))
    ) as DismissMap;
  } catch {
    return {};
  }
}

function persistDismissMap(map: DismissMap): void {
  try {
    window.sessionStorage.setItem(DISMISS_STORAGE_KEY, JSON.stringify(map));
  } catch {
    // ignore
  }
}

export default function GlobalAlertCenter({ enabled, pathname }: Props) {
  const [alerts, setAlerts] = useState<PlatformAlertItem[]>([]);
  const [dismissedUntil, setDismissedUntil] = useState<DismissMap>(() => loadDismissMap());
  const [objectionOpen, setObjectionOpen] = useState(false);
  const [objectionMessage, setObjectionMessage] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const aliveRef = useRef(true);
  const broadcastRef = useRef<BroadcastChannel | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) {
      setAlerts([]);
      setError(null);
      return;
    }
    try {
      const data = await getPendingAlerts();
      if (!aliveRef.current) return;
      setAlerts(data.items || []);
      setError(null);
    } catch (err: any) {
      if (!aliveRef.current) return;
      setError(err?.data?.detail || err?.message || "Falha ao consultar avisos pendentes.");
    }
  }, [enabled]);

  const broadcastSync = useCallback(() => {
    try {
      localStorage.setItem(
        SYNC_STORAGE_KEY,
        JSON.stringify({ at: Date.now(), source: "host-alert-center" })
      );
    } catch {
      // ignore
    }

    try {
      broadcastRef.current?.postMessage({ type: "alerts-sync", at: Date.now() });
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  useEffect(() => {
    persistDismissMap(dismissedUntil);
  }, [dismissedUntil]);

  useEffect(() => {
    if (!enabled) {
      setDismissedUntil({});
      try {
        window.sessionStorage.removeItem(DISMISS_STORAGE_KEY);
      } catch {
        // ignore
      }
      return;
    }

    setDismissedUntil((prev) => {
      const next = Object.fromEntries(
        Object.entries(prev).filter(([alertId, until]) => alerts.some((item) => item.id === alertId) && until > Date.now())
      ) as DismissMap;
      if (JSON.stringify(next) !== JSON.stringify(prev)) {
        persistDismissMap(next);
      }
      return next;
    });
  }, [alerts, enabled]);

  useEffect(() => {
    if (!enabled || typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel(BROADCAST_CHANNEL_NAME);
    broadcastRef.current = channel;
    channel.onmessage = () => {
      void refresh();
    };
    return () => {
      channel.close();
      broadcastRef.current = null;
    };
  }, [enabled, refresh]);

  useEffect(() => {
    void refresh();
    if (!enabled) return;

    const intervalId = window.setInterval(() => void refresh(), 15_000);

    const onFocus = () => void refresh();
    const onVisibility = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === SYNC_STORAGE_KEY) void refresh();
    };

    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibility);
    window.addEventListener("storage", onStorage);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("storage", onStorage);
    };
  }, [enabled, refresh]);

  useEffect(() => {
    if (!enabled) return;
    void refresh();
  }, [enabled, pathname, refresh]);

  useEffect(() => {
    const count = alerts.filter((item) => item.tabBadgeEnabled !== false).length;
    document.title = count > 0 ? `(${count}) ${DEFAULT_TAB_TITLE}` : DEFAULT_TAB_TITLE;
    return () => {
      document.title = DEFAULT_TAB_TITLE;
    };
  }, [alerts]);

  const currentAlert = useMemo(() => {
    const candidate = alerts.find((item) => !isDismissed(dismissedUntil, item.id));
    return candidate ?? null;
  }, [alerts, dismissedUntil]);

  useEffect(() => {
    if (!enabled || !currentAlert) return;
    if (currentAlert.status !== "pending") return;
    void markPendingAlertSeen(currentAlert.id)
      .then(() => refresh())
      .catch(() => {
        // best-effort
      });
  }, [currentAlert, enabled, refresh]);

  const dismissTemporarily = () => {
    if (!currentAlert) return;
    setDismissedUntil((prev) => ({
      ...prev,
      [currentAlert.id]: Date.now() + 2 * 60 * 1000,
    }));
    setObjectionOpen(false);
    setObjectionMessage("");
  };

  const handleConfirm = async () => {
    if (!currentAlert) return;
    setActionBusy(true);
    setError(null);
    try {
      await confirmPendingAlert(currentAlert.id);
      setDismissedUntil((prev) => {
        const next = { ...prev };
        delete next[currentAlert.id];
        return next;
      });
      setObjectionOpen(false);
      setObjectionMessage("");
      broadcastSync();
      await refresh();
    } catch (err: any) {
      setError(err?.data?.detail || err?.message || "Falha ao confirmar aviso.");
    } finally {
      setActionBusy(false);
    }
  };

  const handleObject = async () => {
    if (!currentAlert) return;
    if (currentAlert.objectionRequiresMessage && !objectionMessage.trim()) {
      setError("Digite a mensagem da objeção antes de enviar.");
      return;
    }
    setActionBusy(true);
    setError(null);
    try {
      await objectPendingAlert(currentAlert.id, objectionMessage.trim());
      setDismissedUntil((prev) => {
        const next = { ...prev };
        delete next[currentAlert.id];
        return next;
      });
      setObjectionOpen(false);
      setObjectionMessage("");
      broadcastSync();
      await refresh();
    } catch (err: any) {
      setError(err?.data?.detail || err?.message || "Falha ao registrar objeção.");
    } finally {
      setActionBusy(false);
    }
  };

  if (!enabled || !currentAlert) {
    return null;
  }

  const expiresText = currentAlert.expiresAt
    ? new Date(currentAlert.expiresAt).toLocaleString("pt-BR")
    : "—";

  return (
    <div className="fixed inset-0 z-[120] bg-slate-950/45 backdrop-blur-[1px]">
      <div className="flex min-h-full items-center justify-center p-4">
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="global-alert-title"
          className="w-full max-w-2xl rounded-3xl border border-slate-200 bg-white shadow-2xl"
        >
          <div className="border-b px-6 py-5">
            <div className="flex items-start justify-between gap-4">
              <div>
                <div className="mb-2 flex flex-wrap items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
                  <span
                    className={[
                      "rounded-full px-2.5 py-1 text-[11px] font-semibold",
                      currentAlert.level === "danger"
                        ? "bg-rose-100 text-rose-700"
                        : currentAlert.level === "warning"
                          ? "bg-amber-100 text-amber-700"
                          : "bg-sky-100 text-sky-700",
                    ].join(" ")}
                  >
                    {currentAlert.level}
                  </span>
                  <span>Expira em {expiresText}</span>
                </div>
                <h2 id="global-alert-title" className="text-xl font-semibold tracking-tight text-slate-900">
                  {currentAlert.title}
                </h2>
              </div>

              {currentAlert.allowDismiss && (
                <button
                  type="button"
                  onClick={dismissTemporarily}
                  className="rounded-lg border px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-50"
                >
                  Fechar por agora
                </button>
              )}
            </div>
          </div>

          <div className="px-6 py-5">
            <div className="whitespace-pre-wrap text-sm leading-6 text-slate-700">
              {currentAlert.message}
            </div>

            <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600">
              Este aviso foi enviado para usuários com sessão ativa no momento do disparo.
              A sua resposta fica registrada no painel administrativo.
            </div>

            {error && (
              <div className="mt-4 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {error}
              </div>
            )}

            {currentAlert.objectionEnabled && (
              <div className="mt-5 rounded-2xl border border-slate-200 px-4 py-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-slate-900">Objeção</div>
                    <div className="text-xs text-slate-500">
                      {currentAlert.objectionRequiresMessage
                        ? "Explique sua objeção para que o administrador receba seu retorno."
                        : "Você pode enviar uma mensagem opcional ao administrador."}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      setObjectionOpen((prev) => !prev);
                      setError(null);
                    }}
                    className="rounded-lg border px-3 py-1.5 text-sm text-slate-600 transition hover:bg-slate-50"
                  >
                    {objectionOpen ? "Ocultar" : "Registrar objeção"}
                  </button>
                </div>

                {objectionOpen && (
                  <div>
                    <textarea
                      className="min-h-32 w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                      placeholder="Descreva sua objeção ao aviso."
                      value={objectionMessage}
                      onChange={(e) => setObjectionMessage(e.target.value)}
                    />
                    <div className="mt-2 text-xs text-slate-500">
                      A mensagem será visível para o administrador no histórico do aviso.
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-end gap-3 border-t px-6 py-4">
            {currentAlert.objectionEnabled && objectionOpen && (
              <button
                type="button"
                onClick={handleObject}
                disabled={actionBusy}
                className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-700 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Enviar objeção
              </button>
            )}

            <button
              type="button"
              onClick={handleConfirm}
              disabled={actionBusy}
              className="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Confirmar
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
