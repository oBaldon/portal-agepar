// apps/host/src/pages/CategoryView.tsx
import { useMemo } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import type { Catalog, Block } from "@/types";
import { userCanSeeBlock } from "@/types";
import { useAuth } from "@/auth/AuthProvider";

/**
 * Retorna o caminho “principal” de um bloco.
 *
 * Preferência:
 * 1) `block.navigation[0].path`
 * 2) `block.routes[0].path`
 * 3) `null` quando inexistente.
 *
 * @param block Bloco do catálogo.
 * @returns Caminho principal ou `null`.
 */
function primaryPathOf(block: Block): string | null {
  const nav0 = block.navigation?.[0]?.path;
  const rt0 = block.routes?.[0]?.path;
  return nav0 || rt0 || null;
}

/**
 * Página de uma categoria do catálogo.
 *
 * Comportamento:
 * - Lê o `:id` da URL.
 * - Localiza a categoria correspondente no catálogo.
 * - Lista somente os blocos visíveis para o usuário (RBAC + `hidden`), preservando a ordem declarada.
 *
 * @param catalog Catálogo completo (ou `null` durante o carregamento).
 * @returns JSX da página da categoria.
 */
export default function CategoryView({ catalog }: { catalog: Catalog | null }) {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const { user } = useAuth();

  if (!catalog) {
    return <div className="p-6">Carregando catálogo…</div>;
  }

  const category = useMemo(
    () => catalog.categories?.find((c) => c.id === id),
    [catalog, id]
  );

  const blocks = useMemo(() => {
    return (catalog.blocks || []).filter(
      (b) => b.categoryId === id && userCanSeeBlock(user ?? null, b)
    );
  }, [catalog, id, user]);

  if (!category) {
    return (
      <div className="p-6">
        <div className="mb-2 text-slate-600">Categoria não encontrada.</div>
        <Link to="/inicio" className="text-sky-700 hover:underline text-sm">
          ← Voltar ao início
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">{category.label}</h1>
        <p className="mt-1 text-slate-600">Selecione uma automação desta categoria.</p>
      </div>

      {blocks.length === 0 ? (
        <div className="text-slate-600">
          Nenhuma automação disponível nesta categoria para o seu perfil.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {blocks.map((b) => {
            const to = primaryPathOf(b);
            const disabled = !to;
            return (
              <button
                key={b.name}
                disabled={disabled}
                onClick={() => to && nav(to)}
                className={[
                  "group w-full rounded-2xl border bg-white p-4 text-left shadow-sm transition",
                  disabled ? "cursor-not-allowed opacity-50" : "hover:-translate-y-0.5 hover:shadow-md",
                ].join(" ")}
                title={b.description || b.displayName || b.name}
              >
                <div className="flex items-center justify-between">
                  <div className="text-base font-medium">
                    {b.displayName || b.name}
                  </div>
                  <span
                    className={[
                      "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase",
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
                  <div className="mt-2 line-clamp-2 text-sm text-slate-600">
                    {b.description}
                  </div>
                )}

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

      <div className="mt-6">
        <Link to="/inicio" className="text-sky-700 hover:underline text-sm">
          ← Voltar ao início
        </Link>
      </div>
    </div>
  );
}
