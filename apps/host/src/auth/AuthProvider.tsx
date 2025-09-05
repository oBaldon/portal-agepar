// apps/host/src/auth/AuthProvider.tsx
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { User } from "@/types";
import { getMe, loginWithPassword, logout as apiLogout, configureApiHandlers } from "@/lib/api";

type AuthCtx = {
  user: User | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  login: (identifier: string, password: string, remember?: boolean) => Promise<void>;
  logout: () => Promise<void>;
};

const Ctx = createContext<AuthCtx | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const nav = useNavigate();

  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setErr] = useState<string | null>(null);

  // Interceptadores globais para 401/403
  useEffect(() => {
    configureApiHandlers({
      onUnauthorized: () => {
        // sessão inválida/expirada → zera estado e manda para /login
        setUser(null);
        setErr("Sua sessão expirou. Faça login novamente.");
        nav("/login", { replace: true, state: { reason: "expired" } });
      },
      onForbidden: () => {
        // usuário autenticado mas sem permissão
        nav("/403", { replace: true });
      },
    });
  }, [nav]);

  const refresh = async () => {
    setLoading(true);
    setErr(null);
    try {
      const me = await getMe();
      setUser(me);
    } catch (e: any) {
      // getMe pode disparar onUnauthorized via interceptador; aqui só garantimos estado limpo
      setUser(null);
      setErr(e?.message || "Não autenticado");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const login = async (identifier: string, password: string, remember?: boolean) => {
    setErr(null);
    try {
      const me = await loginWithPassword({ identifier, password, remember_me: !!remember });
      setUser(me);
    } catch (e: any) {
      setErr(e?.message || "Falha no login");
      throw e;
    }
  };

  const logout = async () => {
    try {
      await apiLogout();
    } finally {
      setUser(null);
      setErr(null);
      nav("/login", { replace: true });
    }
  };

  const value = useMemo<AuthCtx>(
    () => ({ user, loading, error, refresh, login, logout }),
    [user, loading, error]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
};

export const useAuth = (): AuthCtx => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider/>");
  return ctx;
};
