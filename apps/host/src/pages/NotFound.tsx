// apps/host/src/pages/NotFound.tsx
/**
 * Página 404 — NotFound
 *
 * Propósito
 * ---------
 * Exibir uma mensagem simples quando a rota acessada não existe.
 *
 * UX/Acessibilidade
 * -----------------
 * - Título semântico <h1> para leitores de tela.
 * - Texto auxiliar com orientação ao usuário.
 *
 * Segurança
 * ---------
 * - Componente puramente estático; não realiza chamadas a APIs.
 *
 * Referências
 * -----------
 * - Definição de rotas no Router (fallback para "*").
 * - Padrões de tipografia e espaçamento do Tailwind no projeto.
 */
export default function NotFound() {
  return (
    <div className="p-8">
      <h1 className="text-xl font-semibold">Página não encontrada</h1>
      <p className="text-slate-600 mt-2">Verifique a URL ou use o menu de navegação.</p>
    </div>
  );
}
