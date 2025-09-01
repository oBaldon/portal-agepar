import { Link, useNavigate } from "react-router-dom";
import type { Catalog, Block } from "@/types";

function primaryPathOf(block: Block): string | null {
  const nav0 = block.navigation?.[0]?.path;
  const rt0 = block.routes?.[0]?.path;
  return nav0 || rt0 || null;
}

export default function HomeDashboard({
  catalog,
  firstPath,
}: {
  catalog: Catalog | null;
  firstPath: string;
}) {
  const nav = useNavigate();

  if (!catalog) {
    return <div className="p-6">Carregando catálogo…</div>;
  }

  const blocks = catalog.blocks ?? [];

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Início</h1>
        <p className="text-slate-600 mt-1">
          Selecione um bloco para abrir a respectiva automação.
        </p>
      </div>

      {blocks.length === 0 ? (
        <div className="text-slate-600">Nenhum bloco no catálogo.</div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {blocks.map((b) => {
            const to = primaryPathOf(b);
            const disabled = !to;
            return (
              <button
                key={b.name}
                disabled={disabled}
                onClick={() => to && nav(to)}
                className={[
                  "group text-left rounded-2xl border p-4 bg-white shadow-sm hover:shadow-md transition w-full",
                  disabled ? "opacity-50 cursor-not-allowed" : "hover:-translate-y-0.5",
                ].join(" ")}
              >
                <div className="flex items-center justify-between">
                  <div className="text-base font-medium">{b.displayName}</div>
                  <span
                    className={[
                      "text-[10px] font-semibold uppercase rounded-full px-2 py-0.5",
                      b.ui.type === "iframe"
                        ? "bg-sky-100 text-sky-700"
                        : "bg-amber-100 text-amber-700",
                    ].join(" ")}
                  >
                    {b.ui.type}
                  </span>
                </div>
                <div className="mt-1 text-sm text-slate-500">
                  v{b.version} • {b.name}
                </div>
                <div className="mt-3 text-sm text-slate-600">
                  {b.navigation?.[0]?.label
                    ? `Abrir: ${b.navigation[0].label}`
                    : "Abrir"}
                </div>
                <div className="mt-4">
                  <span className="inline-flex items-center text-sm font-medium text-sky-700 group-hover:underline">
                    {disabled ? "Indisponível" : "Ir para automação →"}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}

      <div className="mt-8 text-xs text-slate-500">
        Catálogo gerado em {new Date(catalog.generatedAt).toLocaleString()} • Host{" "}
        {catalog.host?.version}
      </div>

      {/* Acesso rápido para o primeiro item do catálogo */}
      {firstPath && (
        <div className="mt-3">
          <Link
            to={firstPath}
            className="text-sm text-sky-700 hover:underline"
          >
            Ir direto para: {firstPath}
          </Link>
        </div>
      )}
    </div>
  );
}
