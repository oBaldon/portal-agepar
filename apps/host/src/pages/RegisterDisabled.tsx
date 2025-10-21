// apps/host/src/pages/RegisterDisabled.tsx
import { Link } from "react-router-dom";

export default function RegisterDisabled() {
  return (
    <div className="min-h-[calc(100vh-56px)] grid place-items-center px-4">
      <div className="w-full max-w-md rounded-2xl border bg-white p-6 shadow-sm">
        <header className="mb-6">
          <h1 className="text-lg font-semibold leading-tight">Auto-registro desativado</h1>
          <p className="text-sm text-slate-600 mt-1">
            A criação de contas pelo portal foi descontinuada.
          </p>
        </header>

        <div className="space-y-3 text-sm">
          <p>
            Novos usuários devem ser cadastrados pelo RH.
            Caso precise de acesso, contate o responsável pelo Portal AGEPAR pelo ramal 4895.
          </p>
          <p>
            <Link to="/login" className="text-sky-700 hover:underline">
              Voltar ao login
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
