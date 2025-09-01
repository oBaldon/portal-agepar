import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login } from "@/lib/api";

export default function Login() {
  const nav = useNavigate();
  const [cpf, setCpf] = useState("");
  const [nome, setNome] = useState("");
  const [email, setEmail] = useState("");
  const [roles, setRoles] = useState("user");
  const [unidades, setUnidades] = useState("AGEPAR");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // apenas para enviar dígitos ao backend
  const digits = (s: string) => s.replace(/\D/g, "");

  // formata visualmente o CPF (XXX.XXX.XXX-XX)
  const formatCpf = (v: string) => {
    const only = v.replace(/\D/g, "").slice(0, 11);
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

  const onSubmit = async (skipParams = false) => {
    setErr(null);
    setLoading(true);
    try {
      if (skipParams) {
        await login();
      } else {
        await login({
          cpf: digits(cpf) || undefined,
          nome: nome || undefined,
          email: email || undefined,
          roles: roles.split(",").map((s) => s.trim()).filter(Boolean),
          unidades: unidades.split(",").map((s) => s.trim()).filter(Boolean),
        });
      }
      // recarrega para refazer o getMe() e cair na Home
      window.location.href = "/";
    } catch (e: any) {
      setErr(e.message || "Erro ao autenticar");
    } finally {
      setLoading(false);
    }
  };

  const fillExample = () => {
    setCpf(formatCpf("12345678901"));
    setNome("Douglas Baldon");
    setEmail("douglas.correa@agepar.pr.gov.br");
    setRoles("user,viewer");
    setUnidades("AGEPAR,DAF");
  };

  const inputCls =
    "border rounded-md px-3 py-2 outline-none focus:ring-2 focus:ring-sky-300 focus:border-sky-400 transition bg-white";

  return (
    <div className="min-h-full grid place-items-center p-6 bg-gradient-to-b from-sky-50 to-white">
      <div className="w-full max-w-md rounded-2xl shadow-xl bg-white p-6 border border-slate-200">
        {/* Branding */}
        <div className="flex items-center gap-2 mb-4">
          <div className="h-9 w-9 rounded-xl bg-sky-600 text-white grid place-items-center font-semibold">
            A
          </div>
          <div>
            <h1 className="text-xl font-semibold leading-tight">Portal AGEPAR</h1>
            <p className="text-xs text-slate-500">Ambiente de desenvolvimento • autenticação mock</p>
          </div>
        </div>

        {err && (
          <div className="mb-3 text-sm text-red-700 bg-red-50 border border-red-200 rounded-md p-2">
            {err}
          </div>
        )}

        <form
          className="grid gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            onSubmit(false);
          }}
        >
          <label className="grid gap-1">
            <span className="text-sm text-slate-600">CPF</span>
            <input
              inputMode="numeric"
              autoComplete="off"
              className={inputCls}
              value={cpf}
              onChange={(e) => setCpf(formatCpf(e.target.value))}
              placeholder="000.000.000-00"
            />
          </label>

          <label className="grid gap-1">
            <span className="text-sm text-slate-600">Nome</span>
            <input
              className={inputCls}
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              placeholder="Seu nome completo"
            />
          </label>

          <label className="grid gap-1">
            <span className="text-sm text-slate-600">Email</span>
            <input
              type="email"
              className={inputCls}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="voce@agepar.pr.gov.br"
            />
          </label>

          {/* Toggle de opções avançadas */}
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="mt-1 text-sm text-sky-700 hover:underline w-fit"
          >
            {showAdvanced ? "Ocultar opções avançadas" : "Mostrar opções avançadas"}
          </button>

          {showAdvanced && (
            <div className="grid sm:grid-cols-2 gap-3">
              <label className="grid gap-1">
                <span className="text-sm text-slate-600">Roles (CSV)</span>
                <input
                  className={inputCls}
                  value={roles}
                  onChange={(e) => setRoles(e.target.value)}
                  placeholder="user,viewer"
                />
              </label>

              <label className="grid gap-1">
                <span className="text-sm text-slate-600">Unidades (CSV)</span>
                <input
                  className={inputCls}
                  value={unidades}
                  onChange={(e) => setUnidades(e.target.value)}
                  placeholder="AGEPAR,DAF"
                />
              </label>
            </div>
          )}

          <div className="flex gap-2 pt-2">
            <button
              type="submit"
              disabled={loading}
              className="px-4 py-2 rounded-md bg-sky-600 text-white hover:bg-sky-700 disabled:opacity-60 disabled:cursor-not-allowed inline-flex items-center gap-2"
            >
              {loading && (
                <span className="h-4 w-4 border-2 border-white/70 border-t-transparent rounded-full animate-spin" />
              )}
              Entrar
            </button>

            <button
              type="button"
              disabled={loading}
              onClick={fillExample}
              className="px-4 py-2 rounded-md border hover:bg-slate-50"
            >
              Exemplo
            </button>

            <button
              type="button"
              disabled={loading}
              onClick={() => onSubmit(true)}
              className="ml-auto px-4 py-2 rounded-md border hover:bg-slate-50"
              title="Cria sessão mock com dados padrão"
            >
              Pular
            </button>
          </div>

          <p className="mt-3 text-xs text-slate-500">
            Em produção, este login será substituído por OIDC (Single Sign-On).
          </p>
        </form>
      </div>
    </div>
  );
}
