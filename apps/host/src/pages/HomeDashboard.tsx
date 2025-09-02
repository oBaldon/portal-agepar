import { Link, useNavigate } from "react-router-dom";
import type { Catalog, Block, User } from "@/types";
import { groupBlocksByCategory, userCanSeeBlock } from "@/types";

/** Escolhe um path “principal” do bloco: prioriza navigation[0].path e cai para routes[0].path */
function primaryPathOf(block: Block): string | null {
  const nav0 = block.navigation?.[0]?.path;
  const rt0 = block.routes?.[0]?.path;
  return nav0 || rt0 || null;
}

export default function HomeDashboard({
  catalog,
  user,
}: {
  catalog: Catalog | null;
  user: User | null;
}) {
  const nav = useNavigate();
  if (!catalog) return <div className="p-6">Carregando catálogo…</div>;

  // RBAC simples + agrupamento por categoria
  const grouped = groupBlocksByCategory(
    (catalog.blocks ?? []).filter((b) => userCanSeeBlock(user, b)),
    catalog.categories
  );

  // quantos cards mostrar por categoria na Home
  const MAX_PER_CATEGORY = 6;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Início</h1>
        <p className="text-slate-600 mt-1">
          Selecione uma categoria ou um bloco para abrir a automação.
        </p>
      </div>

      {grouped.length === 0 ? (
        <div className="text-slate-600">Nenhum bloco disponível.</div>
      ) : (
        grouped.map(({ category, blocks }) => {
          const visible = blocks.slice(0, MAX_PER_CATEGORY);
          const hasMore = blocks.length > visible.length;

          return (
            <section key={category.id} className="mb-8">
              <div className="flex items-baseline justify-between mb-3">
                <h2 className="text-lg font-semibold">{category.label}</h2>

                {hasMore && (
                  <Link
                    to={`/categoria/${category.id}`}
                    className="text-sm text-sky-700 hover:underline"
                  >
                    Ver todos →
                  </Link>
                )}
              </div>

              {visible.length === 0 ? (
                <div className="text-sm text-slate-500">
                  Sem blocos nesta categoria.
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {visible.map((b) => {
                    const to = primaryPathOf(b);
                    const disabled = !to;
                    return (
                      <button
                        key={b.name}
                        disabled={disabled}
                        onClick={() => to && nav(to)}
                        className={[
                          "group text-left rounded-2xl border p-4 bg-white shadow-sm hover:shadow-md transition w-full",
                          disabled
                            ? "opacity-50 cursor-not-allowed"
                            : "hover:-translate-y-0.5",
                        ].join(" ")}
                        title={b.description || b.displayName}
                      >
                        <div className="flex items-center justify-between">
                          <div className="text-base font-medium">
                            {b.displayName}
                          </div>
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

                        {b.description && (
                          <div className="mt-2 text-sm text-slate-600 line-clamp-2">
                            {b.description}
                          </div>
                        )}

                        <div className="mt-3 flex flex-wrap gap-1">
                          {(b.tags ?? []).slice(0, 3).map((t) => (
                            <span
                              key={t}
                              className="text-[10px] px-2 py-0.5 rounded-full border bg-slate-50 text-slate-600"
                            >
                              {t}
                            </span>
                          ))}
                        </div>

                        <div className="mt-4">
                          <span className="inline-flex items-center text-sm font-medium text-sky-700 group-hover:underline">
                            {disabled ? "Indisponível" : "Abrir automação →"}
                          </span>
                        </div>
                      </button>
                    );
                  })}
                </div>
              )}
            </section>
          );
        })
      )}

      <div className="mt-8 text-xs text-slate-500">
        Catálogo gerado em{" "}
        {new Date(catalog.generatedAt).toLocaleString()} • Host{" "}
        {catalog.host?.version}
      </div>
    </div>
  );
}
