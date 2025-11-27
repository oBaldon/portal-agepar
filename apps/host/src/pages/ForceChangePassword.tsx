// apps/host/src/pages/ForceChangePassword.tsx

/**
 * Página de troca obrigatória de senha.
 *
 * Propósito
 * ---------
 * Fluxo dedicado para quando o backend exige `must_change_password = true`.
 * Permite informar a senha atual, definir uma nova senha e confirmar.
 * Em caso de sucesso, atualiza o estado global de autenticação e redireciona
 * o usuário para a página inicial.
 *
 * Acessibilidade/UX
 * -----------------
 * - Botões “Mostrar/Ocultar” para campos de senha.
 * - Mensagens claras de erro (gerais, confirmação e regras do servidor).
 * - Feedback visual durante submissão e após sucesso.
 *
 * Segurança
 * ---------
 * - Não expõe senhas em logs.
 * - Trata respostas estruturadas da API sem alterar a lógica de autenticação.
 *
 * Referências
 * -----------
 * - Convenções de mensagens de erro e formulários (UX writing).
 * - Padrões de feedback e estados de carregamento em formulários web.
 */

import { useMemo, useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { changePassword } from "@/lib/api";
import { useAuth } from "@/auth/AuthProvider";

/**
 * Helper de composição de classes (ignora falsy).
 */
function cls(...xs: (string | false | null | undefined)[]) {
  return xs.filter(Boolean).join(" ");
}

/**
 * Componente principal da página de troca obrigatória de senha.
 *
 * Fluxo
 * -----
 * 1) Se o usuário não precisa mais trocar a senha, redireciona para /inicio.
 * 2) Na submissão, chama a API de changePassword.
 * 3) Em sucesso: informa sucesso, chama `refresh()` para atualizar o usuário
 *    globalmente e navega para /inicio.
 * 4) Em erro: apresenta mensagens de acordo com o status/estrutura retornada.
 */
export default function ForceChangePassword() {
  const nav = useNavigate();
  const { user, refresh } = useAuth();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const [serverErrors, setServerErrors] = useState<string[]>([]);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const [rawError, setRawError] = useState<any>(null);
  const debug = typeof window !== "undefined" && localStorage.getItem("AUTH_DEBUG") === "1";

  const [show, setShow] = useState<{ cur: boolean; neu: boolean; cnf: boolean }>({
    cur: false,
    neu: false,
    cnf: false,
  });

  useEffect(() => {
    if (user && user.must_change_password === false) {
      nav("/inicio", { replace: true });
    }
  }, [user, nav]);

  const canSubmit = useMemo(
    () => !!currentPassword && !!newPassword && !!confirmPassword && !submitting,
    [currentPassword, newPassword, confirmPassword, submitting]
  );

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setServerErrors([]);
    setConfirmError(null);
    setGlobalError(null);
    setRawError(null);

    try {
      await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
        new_password_confirm: confirmPassword,
      });

      setSuccess(true);
      await refresh();
      nav("/inicio", { replace: true });
    } catch (err: any) {
      const status = err?.status ?? err?.response?.status;
      const data = err?.data ?? err?.response?.data ?? {};
      const detail = data?.detail;

      if (debug) setRawError({ status, data });

      if (status === 401 && (detail === "invalid_credentials" || typeof detail === "string")) {
        setGlobalError("Senha atual incorreta.");
      } else if (status === 422 && typeof detail === "object" && detail?.confirm) {
        setConfirmError(String(detail.confirm));
      } else if (status === 400 && typeof detail === "object" && Array.isArray(detail.password)) {
        setServerErrors(detail.password as string[]);
      } else if (typeof detail === "string") {
        setGlobalError(detail);
      } else {
        setGlobalError("Não foi possível trocar a senha. Tente novamente.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  const inputCls =
    "border rounded-md px-3 py-2 outline-none focus:ring-2 focus:ring-sky-300 focus:border-sky-400 transition bg-white";

  return (
    <div className="min-h-[calc(100vh-56px)] grid place-items-center px-4 bg-gradient-to-b from-slate-50 to-slate-100">
      <div className="relative w-full max-w-md rounded-2xl border bg-white/90 backdrop-blur-sm p-6 shadow-md">
        <div className="mb-6 flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-sky-600 text-white grid place-items-center font-semibold shadow-sm">
            A
          </div>
          <div>
            <h1 className="text-lg font-semibold leading-tight">Portal AGEPAR</h1>
            <p className="text-sm text-slate-600">Troca de senha obrigatória</p>
          </div>
        </div>

        {success && (
          <div className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
            Senha alterada com sucesso. Redirecionando…
          </div>
        )}

        {globalError && (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {globalError}
          </div>
        )}

        {serverErrors.length > 0 && (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            <div className="font-medium mb-1">Regras de senha</div>
            <ul className="list-disc pl-5 space-y-1">
              {serverErrors.map((msg, i) => (
                <li key={i}>{msg}</li>
              ))}
            </ul>
          </div>
        )}

        {!success && (
          <form onSubmit={onSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700">Senha atual</label>
              <div className="relative">
                <input
                  id="cur"
                  type={show.cur ? "text" : "password"}
                  autoComplete="current-password"
                  className={cls(inputCls, "mt-1 w-full text-sm pr-16")}
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-2 my-auto h-8 rounded px-2 text-xs text-slate-600 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-300"
                  onClick={() => setShow((s) => ({ ...s, cur: !s.cur }))}
                >
                  {show.cur ? "Ocultar" : "Mostrar"}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700">Nova senha</label>
              <div className="relative">
                <input
                  id="new"
                  type={show.neu ? "text" : "password"}
                  autoComplete="new-password"
                  className={cls(inputCls, "mt-1 w-full text-sm pr-16")}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-2 my-auto h-8 rounded px-2 text-xs text-slate-600 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-300"
                  onClick={() => setShow((s) => ({ ...s, neu: !s.neu }))}
                >
                  {show.neu ? "Ocultar" : "Mostrar"}
                </button>
              </div>
              <p className="mt-1 text-xs text-slate-500">
                Dica: use ao menos 8 caracteres, misturando letras e números.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700">Confirmar nova senha</label>
              <div className="relative">
                <input
                  id="cnf"
                  type={show.cnf ? "text" : "password"}
                  autoComplete="new-password"
                  className={cls(inputCls, "mt-1 w-full text-sm pr-16")}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                />
                <button
                  type="button"
                  className="absolute inset-y-0 right-2 my-auto h-8 rounded px-2 text-xs text-slate-600 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-300"
                  onClick={() => setShow((s) => ({ ...s, cnf: !s.cnf }))}
                >
                  {show.cnf ? "Ocultar" : "Mostrar"}
                </button>
              </div>
              {confirmError && <p className="mt-1 text-xs text-red-600">{confirmError}</p>}
            </div>

            <div className="pt-2 flex items-center justify-between gap-2">
              <button
                type="submit"
                disabled={!canSubmit}
                className={cls(
                  "rounded-md px-4 py-2 text-sm font-medium transition",
                  canSubmit
                    ? "bg-sky-600 text-white hover:bg-sky-700 focus:ring-2 focus:ring-sky-300"
                    : "bg-slate-200 text-slate-500 cursor-not-allowed"
                )}
              >
                Trocar senha
              </button>
              <Link
                to="/"
                className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-700 hover:bg-slate-50"
                replace
              >
                Sair
              </Link>
            </div>
          </form>
        )}

        {debug && rawError && (
          <details className="mt-4 text-xs text-slate-600">
            <summary className="cursor-pointer">DEBUG: erro bruto da API</summary>
            <pre className="mt-2 whitespace-pre-wrap break-words bg-slate-50 p-2 rounded border">
{JSON.stringify(rawError, null, 2)}
            </pre>
          </details>
        )}

        <div className="mt-4 flex items-center justify-between">
          <p className="text-xs text-slate-400">
            Suporte: <span className="tabular-nums">ramal 4895</span>
          </p>
          <Link
            to="/devdocs/"
            target="_blank"
            rel="noopener noreferrer nofollow"
            className="text-[11px] text-slate-400 hover:text-slate-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-slate-300 rounded"
            aria-label="Documentação técnica (desenvolvedores)"
          >
            documentação técnica
          </Link>
        </div>
      </div>
    </div>
  );
}
