from __future__ import annotations

import os
from typing import Callable, Iterable, Optional

import psycopg
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.requests import Request

# Config via env
DATABASE_URL = os.getenv("DATABASE_URL")
SESSION_SLIDING = os.getenv("SESSION_SLIDING", "1") in ("1", "true", "True")
SESSION_RENEW_BEFORE_MINUTES = int(os.getenv("SESSION_RENEW_BEFORE_MINUTES", "30"))

# Prefixos que pulamos (docs, static etc.)
SKIP_PREFIXES: Iterable[str] = tuple(
    (os.getenv("SESSION_MW_SKIP_PREFIXES") or "/openapi,/docs,/redoc,/static,/catalog").split(",")
)

def _pg_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    # conexões curtas; autocommit
    return psycopg.connect(DATABASE_URL, autocommit=True)

class DbSessionMiddleware:
    """
    Valida a sessão server-side (Postgres) em cada request.
    - Se válida: atualiza last_seen_at; e se faltando pouco para expirar, renova expires_at (sliding).
    - Se inválida/expirada/revogada: limpa request.session (efeito prático: usuário "desloga").
    Não intercepta a resposta nem força 401 — mantém retrocompatibilidade.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "") or ""
        if any(path.startswith(p.strip()) for p in SKIP_PREFIXES if p.strip()):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        # A sessão (Starlette SessionMiddleware) precisa estar ativa antes deste middleware.
        db_sess_id: Optional[str] = None
        try:
            db_sess_id = request.session.get("db_session_id")  # type: ignore[assignment]
        except Exception:
            db_sess_id = None

        if not db_sess_id:
            await self.app(scope, receive, send)
            return

        try:
            with _pg_conn() as conn, conn.cursor() as cur:
                # Atualiza last_seen_at e renova expires_at condicionalmente numa única query.
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
                    # Sessão inválida/expirada/revogada → limpa a session do app
                    try:
                        request.session.clear()  # type: ignore[attr-defined]
                    except Exception:
                        pass
                else:
                    # Sessão válida; não precisamos mexer no request.session["user"]
                    # (mantém compat), mas poderíamos armazenar informações em request.state.
                    user_id, created_at, new_expires_at = row  # noqa: F841
                    # Opcional: request.state.user_id = user_id
        except Exception:
            # Falha de banco não deve derrubar a requisição; apenas não valida.
            # (podemos logar no futuro)
            pass

        await self.app(scope, receive, send)
