# Página: Account / Sessions

A página de **Conta → Sessões** exibe e gerencia as **sessões ativas** do usuário.  
Ela se conecta aos endpoints de autenticação do BFF, permitindo **encerrar sessões** e executar **logout**.

---

## 🎯 Objetivos

- Mostrar informações da **sessão atual**.
- Listar **outras sessões ativas** (`GET /api/auth/sessions`) — **futuro**.
- Encerrar sessão específica (`DELETE /api/auth/sessions/{id}`) — **futuro**.
- Encerrar todas as sessões (`POST /api/auth/logout`).

---

## 📐 Layout

- **Título** da página.
- Lista de sessões com:
  - ID da sessão
  - Início (`created_at`)
  - Expiração (`expires_at`)
  - IP aproximado (se disponível)
  - User Agent (se disponível)
- Botão de **Logout** (encerra sessão atual).

---

## 🔧 Implementação (TSX)

```tsx
// apps/host/src/pages/AccountSessions.tsx
import { useEffect, useState } from "react";

type Sess = {
  session_id: string;
  created_at: string;
  expires_at: string;
  ip?: string;
  user_agent?: string;
};

export default function AccountSessions() {
  const [sessions, setSessions] = useState<Sess[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await fetch("/api/auth/sessions", { credentials: "include" });
        if (!r.ok) throw new Error(String(r.status));
        setSessions(await r.json());
      } catch {
        setError("Falha ao carregar sessões (recurso futuro).");
      }
    })();
  }, []);

  async function doLogout() {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
    location.href = "/login";
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-semibold mb-4">Sessões da Conta</h1>

      {error && <div className="text-sm text-gray-600 mb-3">{error}</div>}

      <div className="rounded-2xl border divide-y bg-white shadow-sm">
        {sessions.length === 0 && (
          <div className="p-4 text-gray-600">Sem dados de sessões (futuro).</div>
        )}
        {sessions.map((s) => (
          <div key={s.session_id} className="p-4 flex items-center justify-between gap-4">
            <div className="text-sm">
              <div><span className="font-medium">Sessão:</span> {s.session_id}</div>
              <div>Início: {new Date(s.created_at).toLocaleString()}</div>
              <div>Expira: {new Date(s.expires_at).toLocaleString()}</div>
              {s.ip && <div>IP: {s.ip}</div>}
              {s.user_agent && <div>Agente: {s.user_agent}</div>}
            </div>
            {/* Futuro: botão de encerrar sessão específica */}
            {/* <button className="rounded-xl border px-3 py-1">Encerrar</button> */}
          </div>
        ))}
      </div>

      <div className="mt-6">
        <button
          onClick={doLogout}
          className="rounded-2xl border px-4 py-2 shadow-sm hover:shadow"
        >
          Sair da conta
        </button>
      </div>
    </div>
  );
}
````

---

## 🔐 Considerações de Segurança

* Sempre usar `credentials: "include"` para enviar cookies.
* Logout deve invalidar a sessão no servidor **e** limpar cookies.
* Exibir mensagens genéricas em caso de erro (não vazar detalhes).

---

## 🧪 Testes

* **Carregamento de sessões**: mockar `/api/auth/sessions`.
* **Fallback**: exibir mensagem de erro quando API não disponível.
* **Logout**: ao clicar no botão, deve chamar `/api/auth/logout` e redirecionar para `/login`.

Exemplo de teste (Vitest + RTL):

```tsx
import { render, screen, fireEvent } from "@testing-library/react";
import AccountSessions from "../src/pages/AccountSessions";

test("mostra placeholder quando não há sessões", () => {
  render(<AccountSessions />);
  expect(screen.getByText(/Sem dados de sessões/)).toBeInTheDocument();
});

test("executa logout ao clicar no botão", () => {
  global.fetch = vi.fn().mockResolvedValue({ ok: true });
  render(<AccountSessions />);
  const btn = screen.getByText(/Sair da conta/);
  fireEvent.click(btn);
  expect(global.fetch).toHaveBeenCalledWith("/api/auth/logout", expect.any(Object));
});
```

---

## 🔮 Futuro

* Encerrar sessão específica no front.
* Exibir localização aproximada (GeoIP).
* Notificações de login suspeito.
* Sessões persistentes com refresh token.