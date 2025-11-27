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
  logout as apiLogout,
} from "@/lib/api";

/**
 * AuthProvider — Contexto de autenticação da aplicação.
 *
 * Propósito
 * ---------
 * - Carregar o snapshot do usuário autenticado (`/api/me`);
 * - Expor ações de `login`, `logout` e `refresh`;
 * - Aplicar a regra de obrigatoriedade de troca de senha, redirecionando para
 *   `/auth/force-change-password` quando `must_change_password === true`.
 *
 * Referências
 * -----------
 * - React Context: https://react.dev/reference/react/createContext
 * - React Router v6: https://reactrouter.com/en/main/hooks/use-navigate
 * - Padrão Provider + Hook: https://react.dev/learn/scaling-up-with-reducer-and-context
 */
type AuthCtx = {
  user: User | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  login: (identifier: string, password: string, remember?: boolean) => Promise<void>;
  logout: () => Promise<void>;
  replaceUser: (u: User | null) => void;
};

const Ctx = createContext<AuthCtx | null>(null);

declare global {
  interface Window {
    __AUTH_DEBUG__?: boolean;
  }
}

const getDebug = () =>
  window.__AUTH_DEBUG__ === true ||
  (typeof localStorage !== "undefined" && localStorage.getItem("AUTH_DEBUG") === "1");

function debugLog(...args: any[]) {
  if (getDebug()) console.debug("[Auth]", ...args);
}
function warnLog(...args: any[]) {
  console.warn("[Auth]", ...args);
}

/**
 * Provedor de autenticação. Deve envolver a aplicação.
 */
export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const nav = useNavigate();
  const loc = useLocation();
  const FORCE_PATH = "/auth/force-change-password";

  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setErr] = useState<string | null>(null);

  const didMount = useRef(false);

  const refreshCalls = useRef<number[]>([]);
  const watchdogLimit = 6;
  const watchdogWindowMs = 5000;

  const recordRefreshCall = () => {
    const now = Date.now();
    refreshCalls.current.push(now);
    refreshCalls.current = refreshCalls.current.filter((t) => now - t <= watchdogWindowMs);
    if (refreshCalls.current.length > watchdogLimit) {
      warnLog(
        `Possível loop: ${refreshCalls.current.length} chamadas de refresh()/getMe() em ${
          watchdogWindowMs / 1000
        }s. Verifique efeitos na página atual que possam estar acionando refresh() ou hooks que chamam /api/me.`
      );
    }
  };

  /**
   * Atualiza o snapshot do usuário autenticado a partir do backend.
   * Aplica imediatamente a navegação para a página de troca de senha quando necessário.
   */
  const refresh = useCallback(async () => {
    setLoading(true);
    setErr(null);
    recordRefreshCall();
    debugLog("refresh() start");
    try {
      const me = await getMe();
      debugLog("getMe() ok:", me);
      setUser(me);
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
  }, [nav, FORCE_PATH, loc.pathname]);

  useEffect(() => {
    if (didMount.current) return;
    didMount.current = true;
    debugLog("montou AuthProvider → chamando refresh() inicial");
    void refresh();
  }, [refresh]);

  /**
   * Realiza login por senha e navega conforme a política de troca obrigatória.
   */
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

  /**
   * Efetua logout e limpa o estado local do usuário.
   */
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

  const lastNavAt = useRef(0);
  const NAV_DEBOUNCE_MS = 300;

  /**
   * Guarda de navegação global baseada em `must_change_password`.
   * Evita ping-pong de rotas usando um debounce leve.
   */
  useEffect(() => {
    if (!user) return;

    const now = Date.now();
    if (now - lastNavAt.current < NAV_DEBOUNCE_MS) {
      return;
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

  /**
   * Substitui o snapshot do usuário no estado (ex.: após change-password).
   */
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

/**
 * Hook para consumo do contexto de autenticação.
 * @throws Error quando usado fora de <AuthProvider/>
 */
export const useAuth = (): AuthCtx => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider/>");
  return ctx;
};
