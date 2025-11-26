// apps/host/src/pages/Login.tsx
import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";

const ENABLE_SELF_REGISTER = import.meta.env.VITE_ENABLE_SELF_REGISTER === "true";
// Domínio padrão para completar e-mails sem "@"
const DEFAULT_DOMAIN = import.meta.env.VITE_DEFAULT_LOGIN_DOMAIN || "agepar.pr.gov.br";
const FORCE_PATH = "/auth/force-change-password";

function onlyDigits(s: string) {
  return (s || "").replace(/\D+/g, "");
}

// Considera "numérico-like" entradas só com dígitos e pontuações comuns (., -, /, espaço).
// Ex.: "043.429.199-40" => true | "12345" => true | "joao.silva" => false | "maria@x" => false
function isNumericLike(s: string) {
  const t = (s || "").trim();
  if (!t) return false;
  if (/[a-zA-Z@]/.test(t)) return false;
  return /^[\d.\-\/\s]+$/.test(t);
}

function buildLoginCandidates(raw: string): string[] {
  const id = (raw || "").trim();
  if (!id) return [];
  // Se já tem "@", usa exatamente o que foi digitado
  if (id.includes("@")) return [id];
  // Se é numérico (mesmo com máscara/pontuação), tratar como CPF/ID → usa só dígitos
  if (isNumericLike(id)) return [onlyDigits(id)];
  // Caso contrário, tenta como digitado e também com o domínio padrão
  const canon = `${id}@${String(DEFAULT_DOMAIN).trim().toLowerCase()}`;
  return Array.from(new Set([id, canon])); // dedupe por segurança
}

export default function Login() {
  const nav = useNavigate();
  const { user, login } = useAuth();

  // Se já autenticado, decide destino conforme a flag must_change_password
  const mustChange = (user as any)?.must_change_password === true;
  if (user) return <Navigate to={mustChange ? FORCE_PATH : "/inicio"} replace />;

  // Login real (POST /api/auth/login)
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [capsOn, setCapsOn] = useState(false);
  const [showPwd, setShowPwd] = useState(false);

  const canSubmit = useMemo(
    () => identifier.trim().length > 0 && password.length > 0 && !submitting,
    [identifier, password, submitting]
  );

  // Atalho discreto: Alt + D abre /devdocs/
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.altKey && (e.key === "d" || e.key === "D")) {
        e.preventDefault();
        nav("/devdocs/");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nav]);

  // Dica só aparece quando NÃO é numérico-like e NÃO tem "@"
  const derivedEmailHint = useMemo(() => {
    const id = identifier.trim();
    if (!id || id.includes("@") || isNumericLike(id)) return null;
    return `${id}@${String(DEFAULT_DOMAIN).trim().toLowerCase()}`;
  }, [identifier]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setErr(null);
    try {
      // Tenta sequencialmente: [digitado, digitado@dominio] ou só dígitos se for CPF/máscara
      const candidates = buildLoginCandidates(identifier);
      if (candidates.length === 0) {
        throw new Error("Informe seu e-mail, usuário ou CPF.");
      }
      let lastErr: any = null;
      for (const id of candidates) {
        try {
          await login(id, password, remember);
          lastErr = null;
          break; // sucesso
        } catch (e: any) {
          lastErr = e;
        }
      }
      if (lastErr) throw lastErr;

      // Deixa o AuthProvider/guard global decidir (se precisar força troca, ele redireciona)
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
    <div className="min-h-[calc(100vh-56px)] grid place-items-center px-4 bg-gradient-to-b from-slate-50 to-slate-100">
      <div className="relative w-full max-w-md rounded-2xl border bg-white/90 backdrop-blur-sm p-6 shadow-md">
        {/* Branding */}
        <div className="mb-6 flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-sky-600 text-white grid place-items-center font-semibold shadow-sm">
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
            <label className="block text-sm font-medium text-slate-700">
              E-mail, usuário ou CPF
            </label>
            <input
              type="text"
              inputMode="email"
              autoComplete="username"
              placeholder="joao.silva@agepar.pr.gov.br ou joao.silva ou 00000000000"
              className={`${inputCls} mt-1 w-full text-sm`}
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
            />
            {derivedEmailHint && (
              <p className="mt-1 text-xs text-slate-500">
                Dica: também tentaremos{" "}
                <span className="font-mono">{derivedEmailHint}</span>
              </p>
            )}
          </div>

          <div>
            <div className="flex items-center justify-between">
              <label className="block text-sm font-medium text-slate-700">
                Senha
              </label>
              {/* Indicador de CapsLock (quando ativo) */}
              {capsOn && (
                <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-1.5 py-0.5">
                  Caps Lock ativo
                </span>
              )}
            </div>

            <div className="relative">
              <input
                type={showPwd ? "text" : "password"}
                autoComplete="current-password"
                className={`${inputCls} mt-1 w-full text-sm pr-10`}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyUp={(e) => {
                  // Blindagem: 'key' pode ser undefined/unidentified em alguns eventos
                  const ke = (e as unknown as React.KeyboardEvent<HTMLInputElement>).nativeEvent as KeyboardEvent;
                  const k = (ke as any)?.key ?? "";
                  const isSingleChar = typeof k === "string" && k.length === 1;
                  const isLetter = isSingleChar && /[a-zA-Z]/.test(k);
                  if (isLetter) {
                    const shifted =
                      typeof ke.getModifierState === "function" &&
                      ke.getModifierState("CapsLock");
                    setCapsOn(!!shifted);
                  }
                }}
                onKeyDown={(e) => {
                  const ks = (e as any)?.getModifierState?.("CapsLock");
                  if (typeof ks === "boolean") setCapsOn(ks);
                }}
                onFocus={(e) => {
                  const ks = (e as any)?.getModifierState?.("CapsLock");
                  if (typeof ks === "boolean") setCapsOn(ks);
                }}
              />
              <button
                type="button"
                className="absolute inset-y-0 right-2 my-auto h-8 rounded px-2 text-xs text-slate-600 hover:text-slate-800 focus:outline-none focus:ring-2 focus:ring-sky-300"
                onClick={() => setShowPwd((v) => !v)}
                aria-label={showPwd ? "Ocultar senha" : "Mostrar senha"}
              >
                {showPwd ? "Ocultar" : "Mostrar"}
              </button>
            </div>
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
              {ENABLE_SELF_REGISTER ? (
                <Link to="/registrar" className="text-sky-700 hover:underline">
                  Criar conta
                </Link>
              ) : (
                <span className="text-slate-500">Ramal 4895 para cadastrados</span>
              )}
            </div>
          </div>

          <button
            type="submit"
            disabled={!canSubmit}
            className={[
              "w-full rounded-md px-4 py-2 text-sm font-medium transition",
              canSubmit
                ? "bg-sky-600 text-white hover:bg-sky-700 focus:ring-2 focus:ring-sky-300"
                : "bg-slate-200 text-slate-500 cursor-not-allowed",
            ].join(" ")}
          >
            {submitting ? "Entrando…" : "Entrar"}
          </button>
        </form>

        {/* Rodapé discreto: link para docs de devs (não chama atenção) */}
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

        {/* Dica “invisível” para devs (apenas para leitores de tela) */}
        <span className="sr-only">Atalho: Alt + D abre a documentação técnica.</span>
      </div>
    </div>
  );
}
