// apps/host/src/pages/Register.tsx
import { useMemo, useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "@/auth/AuthProvider";
import { registerUser } from "@/lib/api";

export default function Register() {
  const nav = useNavigate();
  const { user, login } = useAuth();

  // Se já autenticado, manda pra Home
  if (user) return <Navigate to="/inicio" replace />;

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [cpf, setCpf] = useState("");
  const [password, setPassword] = useState("");
  const [password2, setPassword2] = useState("");
  const [remember, setRemember] = useState(true);

  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [okMsg, setOkMsg] = useState<string | null>(null);

  // helpers
  const digits = (s: string) => s.replace(/\D/g, "");
  const formatCpf = (v: string) => {
    const only = digits(v).slice(0, 11);
    const p1 = only.slice(0, 3);
    const p2 = only.slice(3, 6);
    const p3 = only.slice(6, 9);
    const p4 = only.slice(9, 11);
    let out = "";
    if (p1) out = p1;
    if (p2) out = `${p1}.${p2}`;
    if (p3) out = `${p1}.${p2}.${p3}`;
    if (p4) out = `${p1}.${p2}.${p3}-${p4}`;
    return out;
  };

  // validações de front básicas (back-end valida de novo)
  const emailOk = useMemo(() => {
    if (!email) return false;
    // validação simples
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
  }, [email]);

  const cpfOk = useMemo(() => {
    if (!cpf) return false;
    return digits(cpf).length === 11;
  }, [cpf]);

  const passOk = password.length >= 8 && password === password2;

  // precisa de ao menos email OU cpf
  const idProvided = email.trim().length > 0 || digits(cpf).length === 11;

  const canSubmit = useMemo(
    () =>
      !submitting &&
      name.trim().length >= 2 &&
      passOk &&
      idProvided &&
      // se informou email, checa formato; se informou cpf, checa comprimento
      ((!email && cpfOk) || (!cpf && emailOk) || (emailOk && cpfOk)),
    [submitting, name, passOk, idProvided, emailOk, cpfOk, email, cpf]
  );

  const inputCls =
    "border rounded-md px-3 py-2 outline-none focus:ring-2 focus:ring-sky-300 focus:border-sky-400 transition bg-white";

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setErr(null);
    setOkMsg(null);
    try {
      const payload = {
        name: name.trim(),
        email: email.trim() || undefined,
        cpf: digits(cpf) || undefined,
        password,
      };
      await registerUser(payload);

      // login automático usando o identificador preferencial
      const identifier = payload.email ?? payload.cpf!;
      await login(identifier, password, remember);

      setOkMsg("Conta criada com sucesso!");
      nav("/inicio", { replace: true });
    } catch (e: any) {
      setErr(e?.message || "Falha ao registrar");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-56px)] grid place-items-center px-4">
      <div className="w-full max-w-md rounded-2xl border bg-white p-6 shadow-sm">
        {/* Branding */}
        <div className="mb-6 flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-sky-600 text-white grid place-items-center font-semibold">
            A
          </div>
          <div>
            <h1 className="text-lg font-semibold leading-tight">Criar conta</h1>
            <p className="text-sm text-slate-600">Preencha seus dados para acessar o Portal</p>
          </div>
        </div>

        {err && (
          <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {err}
          </div>
        )}
        {okMsg && (
          <div className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
            {okMsg}
          </div>
        )}

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700">Nome completo</label>
            <input
              type="text"
              className={`${inputCls} mt-1 w-full text-sm`}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Seu nome"
            />
            {name && name.trim().length < 2 && (
              <p className="mt-1 text-xs text-red-600">Informe ao menos 2 caracteres.</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700">
              E-mail <span className="text-slate-400 font-normal">(opcional)</span>
            </label>
            <input
              type="email"
              autoComplete="email"
              className={`${inputCls} mt-1 w-full text-sm`}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="voce@agepar.pr.gov.br"
            />
            {email && !emailOk && (
              <p className="mt-1 text-xs text-red-600">E-mail inválido.</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700">
              CPF <span className="text-slate-400 font-normal">(opcional)</span>
            </label>
            <input
              inputMode="numeric"
              autoComplete="off"
              className={`${inputCls} mt-1 w-full text-sm`}
              value={cpf}
              onChange={(e) => setCpf(formatCpf(e.target.value))}
              placeholder="000.000.000-00"
            />
            {cpf && !cpfOk && (
              <p className="mt-1 text-xs text-red-600">CPF deve ter 11 dígitos.</p>
            )}
          </div>

          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-slate-700">Senha</label>
              <input
                type="password"
                autoComplete="new-password"
                className={`${inputCls} mt-1 w-full text-sm`}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Mínimo 8 caracteres"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700">Confirmar senha</label>
              <input
                type="password"
                autoComplete="new-password"
                className={`${inputCls} mt-1 w-full text-sm`}
                value={password2}
                onChange={(e) => setPassword2(e.target.value)}
              />
            </div>
          </div>

          {password && password.length < 8 && (
            <p className="text-xs text-red-600">A senha precisa ter pelo menos 8 caracteres.</p>
          )}
          {password2 && password !== password2 && (
            <p className="text-xs text-red-600">As senhas não coincidem.</p>
          )}
          {!idProvided && (
            <p className="text-xs text-red-600">Informe ao menos e-mail ou CPF.</p>
          )}

          <div className="flex items-center justify-between">
            <label className="inline-flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="h-4 w-4 rounded border-slate-300"
                checked={remember}
                onChange={(e) => setRemember(e.target.checked)}
              />
              Manter conectado após cadastro
            </label>

            <Link to="/login" className="text-sm text-sky-700 hover:underline">
              Já tenho conta
            </Link>
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
            {submitting ? "Criando conta…" : "Criar conta"}
          </button>
        </form>

        <p className="mt-4 text-xs text-slate-500">
          Você pode informar apenas e-mail, apenas CPF ou ambos.
        </p>
      </div>
    </div>
  );
}
