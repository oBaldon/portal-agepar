// apps/host/src/main.tsx
/**
 * Ponto de entrada do Host (SPA).
 *
 * Propósito
 * ---------
 * Monta a árvore de renderização do aplicativo:
 * - inicializa o React 18 via `createRoot`;
 * - aplica o `BrowserRouter` para controle de rotas;
 * - envolve a aplicação com `AuthProvider` para gestão de sessão/usuário;
 * - renderiza o componente raiz `<App/>`.
 *
 * Segurança
 * ---------
 * Este arquivo apenas compõe provedores e o roteador; a proteção de rotas e
 * políticas de autenticação/autorização ocorrem dentro do `AuthProvider` e
 * dos guards configurados em `App`.
 *
 * Referências
 * -----------
 * - React 18: `ReactDOM.createRoot` (Concurrent Rendering).
 * - React Router v6: `BrowserRouter`.
 * - Contexto de Autenticação: `AuthProvider`.
 */

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "@/index.css";
import App from "@/App";
import { AuthProvider } from "@/auth/AuthProvider";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>
);
