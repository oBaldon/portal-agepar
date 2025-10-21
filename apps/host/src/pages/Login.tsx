// apps/host/src/pages/Login.tsx
import { useMemo, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";

const ENABLE_SELF_REGISTER = import.meta.env.VITE_ENABLE_SELF_REGISTER === "true";

export default function Login() {
  const nav = useNavigate();
  const { user, login } = useAuth();

  // Se já autenticado, manda pra Home
  if (user) return <Navigate to="/inicio" replace />;

  // Login real (POST /api/auth/login)
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const canSubmit = useMemo(
    () => identifier.trim().length > 0 && password.length > 0 && !submitting,
    [identifier, password, submitting]
  );

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setErr(null);
    try {
      await login(identifier.trim(), password, remember);
      nav("/inicio", { replace: true });
    } catch (e: any) {
      setErr(e?.message || "Falha no login");
    } finally {
      setSubmitting(false);
    }
  };

  const inputCls =
    "border rounded-md px-3 py-2 outline-none focus:ring-2 focus:ring-sky-300 focus:border-sky-400 transition bg-white";

  return (
    <div className="min-h-[calc(100vh-56px)] grid place-items-center px-4">
      <div className="w-full max-w-md rounded-2xl border bg-white p-6 shadow-sm">
        {/* Branding */}
        <div className="mb-6 flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-sky-600 text-white grid place-items-center font-semibold">
            A
          </div>
          <div>
            <h1 className="text-lg font-semibold leading-tight">Portal AGEPAR</h1>
            <p className="text-sm text-slate-600">Acesse sua conta</p>
          </div>
        </div>

        {/* Erro */}
        {err && (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {err}
          </div>
        )}

        {/* Formulário */}
        <form id="login-form" onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700">E-mail ou CPF</label>
            <input
              type="text"
              inputMode="email"
              autoComplete="username"
              placeholder="seu@email.gov.br ou 00000000000"
              className={`${inputCls} mt-1 w-full text-sm`}
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700">Senha</label>
            <input
              type="password"
              autoComplete="current-password"
              className={`${inputCls} mt-1 w-full text-sm`}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <div className="flex items-center justify-between">
            <label className="inline-flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              Manter conectado
            </label>

            <div className="flex items-center gap-3 text-sm">
              {/* (opcional) rota de recuperação de senha no futuro */}
              {/* <Link to="/recuperar" className="text-sky-700 hover:underline">Esqueci a senha</Link> */}
              {ENABLE_SELF_REGISTER ? (
                <Link to="/registrar" className="text-sky-700 hover:underline">
                  Criar conta
                </Link>
              ) : (
                <span className="text-slate-500">Contate o RH para cadastrados</span>
              )}
            </div>
          </div>

          <button
            type="submit"
            disabled={!canSubmit}
            className={[
              "w-full rounded-md px-4 py-2 text-sm font-medium transition",
              canSubmit
                ? "bg-sky-600 text-white hover:bg-sky-700"
                : "bg-slate-200 text-slate-500 cursor-not-allowed",
            ].join(" ")}
          >
            {submitting ? "Entrando…" : "Entrar"}
          </button>
        </form>
      </div>
    </div>
  );
}
