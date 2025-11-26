# apps/bff/app/auth/middleware.py
"""
Middleware de sessão com persistência em banco (PostgreSQL).

Visão geral
-----------
Este módulo define o `DbSessionMiddleware`, responsável por validar sessões
server-side a cada requisição HTTP, utilizando a tabela `auth_sessions`.
Se a sessão estiver válida, o middleware atualiza `last_seen_at` e, se faltar
pouco para expirar, faz o *sliding expiration* renovando `expires_at` com o
mesmo TTL original. Se estiver inválida, expirada ou revogada, a sessão da
aplicação (cookie) é limpa, provocando o "logout" efetivo no próximo acesso
a rotas que consultam o usuário.

O middleware não intercepta a resposta com 401/403. Ele apenas sincroniza o
estado da sessão; as rotas protegidas continuam aplicando seus próprios guards.

Variáveis de ambiente
---------------------
- DATABASE_URL : string de conexão do PostgreSQL (obrigatória).
- SESSION_SLIDING : "1"/"true" para ativar renovação deslizante do vencimento.
- SESSION_RENEW_BEFORE_MINUTES : janela (em minutos) antes do vencimento em que
  a sessão passa a ser renovada.
- SESSION_MW_SKIP_PREFIXES : lista separada por vírgula de prefixos de caminho
  que o middleware deve ignorar (arquivos estáticos, docs, schema etc.).

Fluxo resumido
--------------
1) Ignora requisições não-HTTP ou cujo `path` comece por um prefixo de exclusão.
2) Lê `db_session_id` da `request.session`. Se não existir, segue o fluxo.
3) Consulta e atualiza `auth_sessions` em uma única query:
   - Atualiza `last_seen_at`.
   - Se `SESSION_SLIDING` estiver ativo e a sessão estiver na janela de
     renovação, estende `expires_at` mantendo o TTL original.
4) Se a atualização não encontrar sessão válida, limpa `request.session`.
5) Erros de banco são intencionamente suprimidos para não derrubar a requisição.

Notas de implementação
----------------------
- Conexões curtas com `autocommit=True`.
- A janela de renovação é controlada por `SESSION_RENEW_BEFORE_MINUTES`.
- `SKIP_PREFIXES` evita custo desnecessário em rotas públicas/estáticas.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

import psycopg
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

DATABASE_URL = os.getenv("DATABASE_URL")
SESSION_SLIDING = os.getenv("SESSION_SLIDING", "1") in ("1", "true", "True")
SESSION_RENEW_BEFORE_MINUTES = int(os.getenv("SESSION_RENEW_BEFORE_MINUTES", "30"))

_raw_skips = os.getenv("SESSION_MW_SKIP_PREFIXES") or "/openapi,/openapi.json,/api/docs,/api/redoc,/static,/catalog"
SKIP_PREFIXES: Iterable[str] = tuple(p.strip() for p in _raw_skips.split(",") if p.strip())


def _pg_conn():
    """
    Cria e retorna uma conexão curta com PostgreSQL usando `DATABASE_URL`.

    Retorna
    -------
    psycopg.Connection
        Conexão com `autocommit=True` pronta para uso.

    Levanta
    -------
    RuntimeError
        Caso `DATABASE_URL` não esteja configurada.

    Observações
    -----------
    - O chamador é responsável por encerrar a conexão (context manager recomendado).
    - `autocommit=True` evita precisar de `commit()` explícito para a atualização.
    """
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL, autocommit=True)


class DbSessionMiddleware:
    """
    Middleware ASGI que valida e renova sessões persistidas em banco.

    Parâmetros
    ----------
    app : ASGIApp
        Aplicação ASGI a ser encadeada após a validação de sessão.

    Comportamento
    -------------
    - Apenas para escopo `http` (WebSocket é encaminhado sem inspeção).
    - Ignora caminhos cujo prefixo esteja em `SKIP_PREFIXES`.
    - Quando existir `db_session_id` na sessão do Starlette, efetua uma única
      query SQL que:
        * verifica existência/validade (não revogada e não expirada);
        * atualiza `last_seen_at`;
        * renova `expires_at` se `SESSION_SLIDING` e janela permitir.
      Se não houver linha válida, a sessão da aplicação é limpa.
    - Qualquer falha de banco é suprimida e a requisição segue normalmente.

    Segurança
    ---------
    - Não altera o status da resposta. Políticas de autorização devem ser
      aplicadas nas rotas (RBAC/guards).
    """

    def __init__(self, app: ASGIApp) -> None:
        """
        Construtor do middleware.

        Parâmetros
        ----------
        app : ASGIApp
            Aplicação ASGI downstream.
        """
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Ponto de entrada do middleware.

        Parâmetros
        ----------
        scope : Scope
            Escopo ASGI da requisição.
        receive : Receive
            Callable para receber mensagens do canal.
        send : Send
            Callable para enviar mensagens ao canal.

        Fluxo detalhado
        ---------------
        1) Encaminha requisições não-HTTP imediatamente.
        2) Se o `path` começar por qualquer prefixo em `SKIP_PREFIXES`, encaminha.
        3) Obtém `db_session_id` de `request.session`. Ausente → encaminha.
        4) Executa a query de atualização/renovação:
           - Atualiza `last_seen_at=now()`.
           - Se `SESSION_SLIDING` e faltam `SESSION_RENEW_BEFORE_MINUTES` para
             expirar, renova `expires_at` mantendo o TTL original
             (`expires_at - created_at`).
           - `RETURNING` indica se havia sessão válida.
        5) Se não houver sessão válida, limpa `request.session`.
        6) Em caso de exceção de banco, suprime e segue o fluxo.
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "") or ""
        if any(path.startswith(prefix) for prefix in SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        db_sess_id: Optional[str] = None
        try:
            db_sess_id = request.session.get("db_session_id")
        except Exception:
            db_sess_id = None

        if not db_sess_id:
            await self.app(scope, receive, send)
            return

        try:
            with _pg_conn() as conn, conn.cursor() as cur:
                cur.execute(
                    """
                    WITH s AS (
                      SELECT id, user_id, created_at, expires_at
                      FROM auth_sessions
                      WHERE id = %s
                        AND revoked_at IS NULL
                        AND expires_at > now()
                    )
                    UPDATE auth_sessions a
                    SET
                      last_seen_at = now(),
                      expires_at = CASE
                        WHEN %s::boolean IS TRUE
                             AND EXISTS (SELECT 1 FROM s)
                             AND (SELECT expires_at FROM s) - now() <= (%s || ' minutes')::interval
                        THEN now() + ((SELECT expires_at FROM s) - (SELECT created_at FROM s))
                        ELSE a.expires_at
                      END
                    FROM s
                    WHERE a.id = s.id
                    RETURNING s.user_id, s.created_at, a.expires_at;
                    """,
                    (db_sess_id, SESSION_SLIDING, SESSION_RENEW_BEFORE_MINUTES),
                )
                row = cur.fetchone()

                if row is None:
                    try:
                        request.session.clear()
                    except Exception:
                        pass
                else:
                    pass
        except Exception:
            pass

        await self.app(scope, receive, send)
