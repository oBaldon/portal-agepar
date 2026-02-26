# apps/bff/app/automations/profile.py
from __future__ import annotations

"""
Automação "Meu Perfil" (self-service).

Propósito
---------
Fornece UI simples (iframe) e endpoints JSON para que qualquer usuário
autenticado possa visualizar e atualizar APENAS seus próprios dados.

Regras de segurança
-------------------
- Não há listagem, busca, nem endpoints parametrizados por `user_id`.
- O usuário alvo é sempre determinado pela sessão (`request.session["user"]["id"]`).
- Campos sensíveis são ignorados/bloqueados no backend (roles, superuser, cpf etc).

Observações
-----------
Este módulo foi desenhado para coexistir com a automação `usuarios` (RH/Admin),
sem alterar suas permissões nem sua UI.
"""

import logging
import pathlib
from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.auth.rbac import require_password_changed
from app.db import _pg, add_audit

logger = logging.getLogger(__name__)

KIND = "profile"
PROFILE_VERSION = "0.1.0"

router = APIRouter(
    prefix="/api/automations/profile",
    tags=["automations:profile"],
    # Segurança: exige autenticação (e bloqueia must_change_password)
    dependencies=[Depends(require_password_changed)],
)

_TEMPLATES_DIR = pathlib.Path(__file__).parent / "templates" / "profile"


def _read_html(name: str) -> str:
    path = _TEMPLATES_DIR / name
    return path.read_text(encoding="utf-8")


def _session_user(req: Request) -> Dict[str, Any]:
    user = req.session.get("user")
    if not isinstance(user, dict):
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


def _session_user_id(req: Request) -> Optional[str]:
    user = _session_user(req)
    uid = user.get("id")
    return str(uid) if uid else None


class ProfileUpdateIn(BaseModel):
    """
    Atualização parcial do perfil (self-only).

    Notas
    -----
    - `extra="ignore"` garante que campos proibidos enviados pelo cliente sejam
      descartados silenciosamente (ex.: roles, is_superuser, cpf).
    - Campos aqui representam apenas o que o usuário pode editar diretamente.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    nome_completo: Optional[str] = Field(default=None, min_length=3, max_length=200)
    rg: Optional[str] = Field(default=None, max_length=50)
    data_nascimento: Optional[str] = Field(default=None, description="YYYY-MM-DD")
    email_principal: Optional[str] = Field(default=None, max_length=320)
    email_institucional: Optional[str] = Field(default=None, max_length=320)
    telefone_principal: Optional[str] = Field(default=None, max_length=50)
    ramal: Optional[str] = Field(default=None, max_length=20)
    endereco: Optional[str] = Field(default=None, max_length=400)
    dependentes_qtde: Optional[int] = Field(default=None, ge=0, le=99)
    formacao_nivel_medio: Optional[bool] = None

    @field_validator("data_nascimento")
    @classmethod
    def _validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        # valida ISO básico (YYYY-MM-DD)
        try:
            date.fromisoformat(v)
        except Exception as exc:
            raise ValueError("data_nascimento deve estar no formato YYYY-MM-DD") from exc
        return v

    @field_validator("email_principal", "email_institucional")
    @classmethod
    def _strip_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        vv = v.strip()
        return vv if vv else None


def _snapshot_self(user_id: str) -> Dict[str, Any]:
    """
    Snapshot mínimo para o perfil (sem listagem e sem joins pesados).

    Mantém o shape compatível com a UI do RH (`usuarios/detail_edit.html`),
    retornando:
      { user: {...}, employment: {...}, educacao: {...} }
    """
    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT
              u.id::text          AS id,
              u.name              AS nome_completo,
              u.cpf,
              u.rg,
              u.id_funcional,
              u.data_nascimento   AS data_nascimento,
              u.email             AS email_principal,
              u.email_institucional,
              u.telefone_principal,
              u.ramal,
              u.endereco,
              u.saldo_ferias,
              u.saldo_ferias_ano,
              u.dependentes_qtde,
              u.formacao_nivel_medio,
              u.status            AS status_usuario
            FROM users u
            WHERE u.id::text = %s
            """,
            (user_id,),
        )
        urow = cur.fetchone()
        if not urow:
            raise HTTPException(status_code=404, detail="user_not_found")

    # Estrutura compatível com a UI (mesmo que alguns blocos fiquem vazios)
    return {
        "user": urow,
        "employment": {},   # vínculo é RH/admin; perfil não edita aqui
        "educacao": {},     # educação detalhada é RH/admin; perfil pode ser expandido depois
    }


def _apply_profile_update(user_id: str, payload: ProfileUpdateIn, actor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Atualiza colunas permitidas do usuário e retorna snapshot atualizado.
    """
    # Mapeamento: campo do payload -> coluna no banco
    col_map = {
        "nome_completo": "name",
        "rg": "rg",
        "data_nascimento": "data_nascimento",
        "email_principal": "email",
        "email_institucional": "email_institucional",
        "telefone_principal": "telefone_principal",
        "ramal": "ramal",
        "endereco": "endereco",
        "dependentes_qtde": "dependentes_qtde",
        "formacao_nivel_medio": "formacao_nivel_medio",
    }

    data = payload.model_dump(exclude_unset=True)
    if not data:
        # nada para salvar
        return _snapshot_self(user_id)

    set_parts = []
    params = []
    changes: Dict[str, Any] = {}

    for k, v in data.items():
        col = col_map.get(k)
        if not col:
            continue
        # Normalizações pequenas
        if k == "nome_completo" and isinstance(v, str):
            v = v.strip()
            if not v:
                continue
        if k == "data_nascimento" and isinstance(v, str):
            v = date.fromisoformat(v)  # já validado
        set_parts.append(f"{col} = %s")
        params.append(v)
        changes[k] = v.isoformat() if isinstance(v, date) else v

    if not set_parts:
        return _snapshot_self(user_id)

    params.append(user_id)

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            UPDATE users
               SET {", ".join(set_parts)},
                   updated_at = now()
             WHERE id::text = %s
            """,
            tuple(params),
        )

    try:
        add_audit(
            kind=KIND,
            action="update",
            actor=actor,
            meta={"user_id": user_id, "changes": changes},
        )
    except Exception:
        # auditoria não deve quebrar UX
        logger.exception("Falha ao registrar auditoria do profile.update")

    return _snapshot_self(user_id)


@router.get("/ui", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    """
    UI embutida via iframe no Host.
    """
    return HTMLResponse(_read_html("ui.html"))


@router.get("/me")
def get_me(request: Request) -> Dict[str, Any]:
    """
    Retorna os dados do usuário autenticado (self-only).
    """
    uid = _session_user_id(request)

    # Modo MOCK / sessão sem user_id em banco
    if not uid:
        u = _session_user(request)
        # devolve um shape compatível com a UI
        return {
            "user": {
                "id": None,
                "nome_completo": u.get("nome") or u.get("name") or "",
                "email_principal": u.get("email") or "",
                "cpf": u.get("cpf"),
                "status_usuario": "active",
            },
            "employment": {},
            "educacao": {},
        }

    return _snapshot_self(uid)


@router.put("/me")
def update_me(request: Request, payload: ProfileUpdateIn) -> Dict[str, Any]:
    """
    Atualiza o próprio perfil (self-only).
    """
    actor = _session_user(request)
    uid = _session_user_id(request)

    # Modo MOCK: atualiza apenas a sessão (sem BD)
    if not uid:
        data = payload.model_dump(exclude_unset=True)
        if "nome_completo" in data and isinstance(data["nome_completo"], str):
            actor["nome"] = data["nome_completo"].strip()
        if "email_principal" in data and isinstance(data["email_principal"], str):
            actor["email"] = data["email_principal"].strip()
        request.session["user"] = actor
        return {
            "user": {
                "id": None,
                "nome_completo": actor.get("nome") or actor.get("name") or "",
                "email_principal": actor.get("email") or "",
                "cpf": actor.get("cpf"),
                "status_usuario": "active",
            },
            "employment": {},
            "educacao": {},
        }

    out = _apply_profile_update(uid, payload, actor)

    # Atualiza snapshot mínimo em sessão para refletir no header (nome/email)
    try:
        u = request.session.get("user") or {}
        if isinstance(u, dict):
            uu = out.get("user") or {}
            if isinstance(uu, dict):
                if uu.get("nome_completo"):
                    u["nome"] = uu["nome_completo"]
                if uu.get("email_principal"):
                    u["email"] = uu["email_principal"]
                request.session["user"] = u
    except Exception:
        logger.exception("Falha ao atualizar snapshot de sessão após profile.update")

    return out