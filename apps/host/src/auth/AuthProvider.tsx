// apps/host/src/auth/AuthProvider.tsx
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { User } from "@/types";
import { getMe, loginWithPassword, logout as apiLogout } from "@/lib/api";

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
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setErr] = useState<string | null>(null);

  const refresh = async () => {
    setLoading(true);
    setErr(null);
    try {
      const me = await getMe();
      setUser(me);
    } catch (e: any) {
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
