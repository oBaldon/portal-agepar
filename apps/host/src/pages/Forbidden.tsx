// apps/host/src/pages/Forbidden.tsx
import { Link } from "react-router-dom";

export default function Forbidden() {
  return (
    <div className="p-8 max-w-xl mx-auto text-center">
      <div className="text-5xl mb-3">🚫</div>
      <h1 className="text-2xl font-semibold">Acesso negado</h1>
      <p className="mt-2 text-slate-600">
        Você não tem permissão para acessar este conteúdo.
      </p>
      <div className="mt-6 flex items-center justify-center gap-3">
        <Link to="/inicio" className="px-4 py-2 rounded-md border hover:bg-slate-50">
          Ir para início
        </Link>
        <Link to="/conta/sessoes" className="px-4 py-2 rounded-md border hover:bg-slate-50">
          Ver minhas sessões
        </Link>
      </div>
    </div>
  );
}
