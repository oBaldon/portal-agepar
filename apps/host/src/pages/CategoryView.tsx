import { useMemo } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import type { Catalog, Block } from "@/types";
import { userCanSeeBlock } from "@/types";
import { useAuth } from "@/auth/AuthProvider";

/** Caminho “principal” do bloco (prefere navigation[0].path, cai pra routes[0].path). */
function primaryPathOf(block: Block): string | null {
  const nav0 = block.navigation?.[0]?.path;
  const rt0 = block.routes?.[0]?.path;
  return nav0 || rt0 || null;
}

/**
 * Página da categoria:
 * - Lê o :id da URL
 * - Busca a categoria por id no catálogo
 * - Lista APENAS os blocos visíveis para o usuário atual (RBAC), ignorando hidden
 * - Preserva a ordem dos blocos exatamente como vem no catálogo (sem sort manual)
 */
export default function CategoryView({ catalog }: { catalog: Catalog | null }) {
  const { id } = useParams<{ id: string }>();
  const nav = useNavigate();
  const { user } = useAuth(); // <- pega o usuário autenticado (tem roles, is_superuser, etc.)

  if (!catalog) {
    return <div className="p-6">Carregando catálogo…</div>;
  }

  const category = useMemo(
    () => catalog.categories?.find((c) => c.id === id),
    [catalog, id]
  );

  // Filtra os blocos desta categoria aplicando RBAC (userCanSeeBlock)
  const blocks = useMemo(() => {
    return (catalog.blocks || []).filter(
      (b) => b.categoryId === id && userCanSeeBlock(user ?? null, b)
    );
    // OBS: Sem sort extra — mantemos a ordem já definida no JSON do catálogo
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
        <p className="text-slate-600 mt-1">
          Selecione uma automação desta categoria.
        </p>
      </div>

      {blocks.length === 0 ? (
        <div className="text-slate-600">Nenhuma automação disponível nesta categoria para o seu perfil.</div>
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
                  "group text-left rounded-2xl border p-4 bg-white shadow-sm transition w-full",
                  disabled
                    ? "opacity-50 cursor-not-allowed"
                    : "hover:shadow-md hover:-translate-y-0.5",
                ].join(" ")}
                title={b.description || b.displayName || b.name}
              >
                <div className="flex items-center justify-between">
                  <div className="text-base font-medium">{b.displayName || b.name}</div>
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
