# apps/bff/app/auth/vacation_balance.py
from __future__ import annotations

from datetime import datetime
from typing import Union
import uuid

import psycopg


UserId = Union[str, uuid.UUID]


def current_year() -> int:
    """
    Retorna o ano corrente considerando o timezone do servidor (processo).
    """
    return datetime.now().astimezone().year


def ensure_user_vacation_columns(conn: psycopg.Connection) -> None:
    """
    Garante que a tabela `users` possua as colunas necessárias para o saldo de férias.

    - Executa ALTER TABLE idempotente (IF NOT EXISTS).
    - Faz backfill para cobrir cenários em que colunas já existam mas estejam nulas/sem default.
    - Reforça DEFAULT e NOT NULL.

    Observação:
    - Esta função supõe que a tabela `users` já existe (criada pelo init_db.sql).
    """
    with conn.cursor() as cur:
        # Garante que a tabela users existe (falha com mensagem clara se não existir)
        cur.execute("SELECT to_regclass('public.users')")
        reg = cur.fetchone()
        if not reg or reg[0] is None:
            raise RuntimeError(
                "Tabela 'users' não encontrada no banco. "
                "Verifique se o schema foi inicializado (infra/sql/init_db.sql)."
            )

        # DDL pedido (idempotente)
        cur.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS saldo_ferias integer NOT NULL DEFAULT 30;"
        )
        cur.execute(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS saldo_ferias_ano integer NOT NULL "
            "DEFAULT EXTRACT(YEAR FROM now())::int;"
        )

        # Backfill (cobre casos antigos: colunas já existiam e eram NULL/sem NOT NULL)
        cur.execute("UPDATE users SET saldo_ferias = 30 WHERE saldo_ferias IS NULL;")
        cur.execute(
            "UPDATE users "
            "SET saldo_ferias_ano = EXTRACT(YEAR FROM now())::int "
            "WHERE saldo_ferias_ano IS NULL;"
        )

        # Reforça defaults (caso colunas existam mas sem DEFAULT)
        cur.execute("ALTER TABLE users ALTER COLUMN saldo_ferias SET DEFAULT 30;")
        cur.execute(
            "ALTER TABLE users ALTER COLUMN saldo_ferias_ano "
            "SET DEFAULT EXTRACT(YEAR FROM now())::int;"
        )

        # Reforça NOT NULL (caso colunas existam mas sejam nullable)
        cur.execute("ALTER TABLE users ALTER COLUMN saldo_ferias SET NOT NULL;")
        cur.execute("ALTER TABLE users ALTER COLUMN saldo_ferias_ano SET NOT NULL;")


def ensure_vacation_balance(conn: psycopg.Connection, user_id: UserId) -> int:
    """
    Garante que o usuário tenha saldo de férias consistente e atualizado.

    Regras:
    - Se saldo não existir/preenchido → saldo_ferias = 30 e saldo_ferias_ano = ano_atual
    - Se saldo_ferias_ano < ano_atual → incrementa 30 * (ano_atual - saldo_ferias_ano)
      e atualiza saldo_ferias_ano = ano_atual

    Retorna:
    - saldo_ferias (int) após a normalização/atualização.

    Observações:
    - Esta função assume que as colunas já existem. Em geral, chame
      `ensure_user_vacation_columns(conn)` no startup do app.
    - Implementação feita em 1 UPDATE + RETURNING para ser atômica.
    """
    y = current_year()
    uid = str(user_id) if not isinstance(user_id, str) else user_id

    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE users
            SET
              saldo_ferias =
                CASE
                  WHEN COALESCE(saldo_ferias_ano, %s) < %s
                    THEN COALESCE(saldo_ferias, 30)
                         + (30 * (%s - COALESCE(saldo_ferias_ano, %s)))
                  ELSE COALESCE(saldo_ferias, 30)
                END,
              saldo_ferias_ano =
                CASE
                  WHEN COALESCE(saldo_ferias_ano, %s) < %s
                    THEN %s
                  ELSE COALESCE(saldo_ferias_ano, %s)
                END
            WHERE id = %s::uuid
            RETURNING saldo_ferias
            """,
            (y, y, y, y, y, y, y, y, uid),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Usuário não encontrado para id={uid}")

        saldo = row[0]
        # Segurança extra: psycopg pode retornar Decimal/None em casos estranhos; forçamos int.
        return int(saldo)
