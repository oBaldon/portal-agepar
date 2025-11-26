// apps/host/src/auth/AuthProvider.tsx
import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  useCallback,
  useRef,
} from "react";
import { useLocation, useNavigate } from "react-router-dom";
import type { User } from "@/types";
import {
  getMe,
  loginWithPassword,
  logout as apiLogout, /* configureApiHandlers */
} from "@/lib/api";

type AuthCtx = {
  user: User | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  login: (identifier: string, password: string, remember?: boolean) => Promise<void>;
  logout: () => Promise<void>;
  replaceUser: (u: User | null) => void; // <-- novo: injeta snapshot do backend sem refresh
};

const Ctx = createContext<AuthCtx | null>(null);

// ---------- Debug helpers ----------
declare global {
  interface Window {
    __AUTH_DEBUG__?: boolean;
  }
}
const getDebug = () =>
  window.__AUTH_DEBUG__ === true ||
  typeof localStorage !== "undefined" && localStorage.getItem("AUTH_DEBUG") === "1";

function debugLog(...args: any[]) {
  if (getDebug()) console.debug("[Auth]", ...args);
}
function warnLog(...args: any[]) {
  console.warn("[Auth]", ...args);
}
// -----------------------------------

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const nav = useNavigate();
  const loc = useLocation();
  const FORCE_PATH = "/auth/force-change-password";

  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setErr] = useState<string | null>(null);

  // Evita rodar refresh duas vezes no StrictMode em DEV
  const didMount = useRef(false);

  // Watchdog de spam de refresh/getMe
  const refreshCalls = useRef<number[]>([]);
  const watchdogLimit = 6;         // no máximo 6 refresh em 5s
  const watchdogWindowMs = 5000;

  const recordRefreshCall = () => {
    const now = Date.now();
    refreshCalls.current.push(now);
    // mantém janela deslizante de 5s
    refreshCalls.current = refreshCalls.current.filter(t => now - t <= watchdogWindowMs);
    if (refreshCalls.current.length > watchdogLimit) {
      warnLog(
        `Possível loop: ${refreshCalls.current.length} chamadas de refresh()/getMe() em ${watchdogWindowMs/1000}s. ` +
        `Verifique efeitos na página atual que possam estar acionando refresh() ou hooks que chamam /api/me.`
      );
    }
  };

  const refresh = useCallback(async () => {
    setLoading(true);
    setErr(null);
    recordRefreshCall();
    debugLog("refresh() start");
    try {
      const me = await getMe();
      debugLog("getMe() ok:", me);
      setUser(me);
      // Enforce imediatamente após carregar o usuário
      if (me?.must_change_password === true && loc.pathname !== FORCE_PATH) {
        debugLog("must_change_password=true → navegando para", FORCE_PATH);
        nav(FORCE_PATH, { replace: true });
      }
    } catch (e: any) {
      debugLog("getMe() erro:", e?.message || e);
      setUser(null);
      setErr(e?.message || "Não autenticado");
    } finally {
      setLoading(false);
      debugLog("refresh() end");
    }
  // IMPORTANTE: não dependa de loc.pathname aqui para não recriar a função e re-disparar o effect
  }, [nav, FORCE_PATH, loc.pathname]); // se preferir ainda mais estável, remova loc.pathname dos deps

  useEffect(() => {
    if (didMount.current) return;
    didMount.current = true;
    debugLog("montou AuthProvider → chamando refresh() inicial");
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (identifier: string, password: string, remember?: boolean) => {
      setErr(null);
      debugLog("login() →", { identifier, remember });
      try {
        const me = await loginWithPassword({
          identifier,
          password,
          remember_me: !!remember,
        });
        debugLog("login ok:", me);
        setUser(me);
        // Se o backend exige troca, força a rota dedicada
        if (me?.must_change_password === true) {
          debugLog("login: must_change_password=true →", FORCE_PATH);
          nav(FORCE_PATH, { replace: true });
        } else {
          nav("/inicio", { replace: true });
        }
      } catch (e: any) {
        setErr(e?.message || "Falha no login");
        debugLog("login erro:", e?.message || e);
        throw e;
      }
    },
    [nav, FORCE_PATH]
  );

  const logout = useCallback(async () => {
    debugLog("logout()");
    try {
      await apiLogout();
    } finally {
      setUser(null);
      setErr(null);
      if (loc.pathname !== "/login") nav("/login", { replace: true });
    }
  }, [nav, loc.pathname]);

  // Debounce anti-ping-pong de navegação
  const lastNavAt = useRef(0);
  const NAV_DEBOUNCE_MS = 300;

  // Guard global de navegação:
  // - Se a flag está true, qualquer tentativa de sair da página de troca redireciona de volta.
  // - Se a flag foi limpa e o usuário permanece na página de troca, manda para a Home.
  useEffect(() => {
    if (!user) return;

    const now = Date.now();
    if (now - lastNavAt.current < NAV_DEBOUNCE_MS) {
      return; // evita navegações back-to-back
    }

    const must = (user as any)?.must_change_password === true;
    if (must && loc.pathname !== FORCE_PATH) {
      lastNavAt.current = now;
      debugLog("guard: must_change_password=true →", FORCE_PATH);
      nav(FORCE_PATH, { replace: true });
    } else if (!must && loc.pathname === FORCE_PATH) {
      lastNavAt.current = now;
      debugLog("guard: must_change_password=false e estamos no FORCE_PATH → /inicio");
      nav("/inicio", { replace: true });
    }
  }, [user?.must_change_password, loc.pathname, nav, FORCE_PATH]);

  // Expor forma controlada de substituir o usuário (ex.: após change-password)
  const replaceUser = useCallback((u: User | null) => {
    debugLog("replaceUser()", u);
    setUser(u);
  }, []);

  const value = useMemo<AuthCtx>(
    () => ({ user, loading, error, refresh, login, logout, replaceUser }),
    [user, loading, error, refresh, login, logout, replaceUser]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
};

export const useAuth = (): AuthCtx => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider/>");
  return ctx;
};
