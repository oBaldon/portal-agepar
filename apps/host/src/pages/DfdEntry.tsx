// src/pages/DfdEntry.tsx
import { useMemo } from "react";
import { useNavigate, useLocation } from "react-router-dom";

/**
 * Tela de entrada do DFD
 *
 * Objetivo: antes de abrir o formulário do DFD, o usuário escolhe
 * qual modelo deseja acessar:
 * - DFD Padrão
 * - DFD Capacitação
 *
 * Esta escolha redireciona para rotas internas do Host:
 * /dfd/padrao e /dfd/capacitacao
 *
 * Observação: a UI real do DFD continua sendo servida pelo BFF via iframe.
 */
export default function DfdEntry() {
  const nav = useNavigate();
  const loc = useLocation();

  const nextParam = useMemo(() => {
    const sp = new URLSearchParams(loc.search);
    const next = sp.get("next");
    return next && next.startsWith("/") ? next : null;
  }, [loc.search]);

  const go = (tipo: "padrao" | "capacitacao") => {
    const target = tipo === "padrao" ? "/dfd/padrao" : "/dfd/capacitacao";
    nav(target + (nextParam ? `?next=${encodeURIComponent(nextParam)}` : ""), {
      replace: true,
    });
  };

  return (
    <div className="p-6">
      <div className="mx-auto max-w-3xl">
        <h1 className="text-xl font-semibold tracking-tight">
          DFD — Documento de Formalização da Demanda
        </h1>
        <p className="mt-2 text-slate-600">
          Selecione qual versão do DFD você deseja preencher.
        </p>

        {/* “Popup” (modal simples) */}
        <div className="mt-8 relative">
          <div className="absolute inset-0 bg-slate-900/20 rounded-2xl" aria-hidden="true" />
          <div className="relative bg-white rounded-2xl shadow-sm border p-6">
            <div className="flex items-start gap-3">
              <div className="h-10 w-10 rounded-xl bg-sky-600 text-white grid place-items-center font-semibold">
                D
              </div>
              <div className="flex-1">
                <h2 className="text-lg font-semibold">Escolha o tipo de DFD</h2>
                <p className="mt-1 text-sm text-slate-600">
                  Você pode gerar o DFD no formato padrão ou no formato de capacitação.
                </p>
              </div>
            </div>

            <div className="mt-6 grid gap-3 sm:grid-cols-2">
              <button
                type="button"
                onClick={() => go("padrao")}
                className="text-left border rounded-xl p-4 hover:bg-slate-50 transition"
              >
                <div className="font-semibold">DFD Padrão</div>
                <div className="mt-1 text-sm text-slate-600">
                  Preenchimento completo com itens livres (modelo atual).
                </div>
              </button>

              <button
                type="button"
                onClick={() => go("capacitacao")}
                className="text-left border rounded-xl p-4 hover:bg-slate-50 transition"
              >
                <div className="font-semibold">DFD Capacitação</div>
                <div className="mt-1 text-sm text-slate-600">
                  Variante para demandas de capacitação (campos e tabelas específicas).
                </div>
              </button>
            </div>

            <div className="mt-4 text-xs text-slate-500">
              Dica: se você tiver dúvida sobre qual opção escolher, consulte o time de Compras.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
