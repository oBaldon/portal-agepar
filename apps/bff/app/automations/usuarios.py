# apps/bff/app/automations/usuarios.py
from __future__ import annotations

import logging
import os
import pathlib
import re
from typing import Any, Dict, List, Optional, Literal
from secrets import choice
from datetime import date, datetime, time
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from argon2 import PasswordHasher

from app.auth.rbac import require_roles_any
from app.db import insert_submission, get_submission, list_submissions_admin, add_audit, _pg  # type: ignore

logger = logging.getLogger(__name__)
# === Config (histórico) ===
# Máximo de eventos de histórico (somatório paginado) e tamanho do lote por consulta
USUARIOS_HISTORY_MAX = int(os.getenv("USUARIOS_HISTORY_MAX", "20000"))
USUARIOS_HISTORY_BATCH = int(os.getenv("USUARIOS_HISTORY_BATCH", "1000"))

# ---------------------------------------------------------------------
# Config & RBAC
# ---------------------------------------------------------------------
REQUIRED_ROLES = ("rh", "admin")
TPL_DIR = pathlib.Path(__file__).resolve().parent / "templates" / "usuarios"

# UO padrão enquanto a modelagem estiver "desabilitada"
DEFAULT_ORG_UNIT_CODE = "AGEPAR"

router = APIRouter(
    prefix="/api/automations/usuarios",
    tags=["automations:usuarios"],
    dependencies=[Depends(require_roles_any(*REQUIRED_ROLES))],
)

hasher = PasswordHasher()

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
CPF_RE = re.compile(r"\D+")


def norm_cpf(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    v = CPF_RE.sub("", v or "")
    if v == "":
        return None
    if len(v) != 11 or not v.isdigit():
        raise HTTPException(status_code=422, detail="CPF deve conter 11 dígitos numéricos.")
    return v


def safe_digits(s: str) -> str:
    return CPF_RE.sub("", s or "")


def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))


def err_json(
    status: int,
    *,
    code: str,
    message: str,
    details: Any = None,
    hint: Optional[str] = None,
    received: Any = None,
):
    content: Dict[str, Any] = {"error": code, "message": message}
    if details is not None:
        content["details"] = details
    if hint is not None:
        content["hint"] = hint
    if received is not None:
        content["received"] = received
    return JSONResponse(status_code=status, content=content)


def _json_safe(obj: Any) -> Any:
    """Converte recursivamente para tipos serializáveis em JSON (psycopg json)."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, (date, datetime, time)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    try:
        return str(obj)
    except Exception:
        return None


def _read_html(name: str) -> str:
    path = TPL_DIR / name
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        # fallback mínimo
        return """<!doctype html>
<html lang="pt-br">
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Usuários (RH)</title>
<style>body{font-family:ui-sans-serif,system-ui;margin:16px}.card{border:1px solid #ddd;padding:16px;border-radius:12px}</style>
</head>
<body>
  <h1>Usuários (RH)</h1>
  <div class="card">
    <p>Contratos disponíveis em <code>/api/automations/usuarios/*</code>.</p>
    <ul>
      <li>GET <code>/schema</code></li>
      <li>GET <code>/users</code></li>
      <li>POST <code>/users</code></li>
    </ul>
    <p style="color:#6b7280">Para reset de senha e gestão de roles, use o módulo <b>Admin — Contas & Roles</b>.</p>
  </div>
</body>
</html>"""


# PIN temporário numérico de 4 dígitos
_DIGITS = "0123456789"


def gen_temp_pin() -> str:
    return "".join(choice(_DIGITS) for _ in range(4))


def map_user_status_from_employment(v: Literal["ativo", "inativo"]) -> Literal["active", "blocked"]:
    return "active" if v == "ativo" else "blocked"


# ---------------------------------------------------------------------
# Schemas (núcleo + vínculos, modelo relacional)
# ---------------------------------------------------------------------
# Formação comum
class GraduacaoIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    curso: str = Field(min_length=2)
    instituicao: Optional[str] = None
    conclusao_data: Optional[str] = None  # YYYY-MM-DD


class PosGraduacaoIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    curso: str = Field(min_length=2)
    tipo: Optional[Literal["especializacao", "mestrado", "doutorado", "pos"]] = None
    instituicao: Optional[str] = None
    conclusao_data: Optional[str] = None  # YYYY-MM-DD


class FormacaoIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    nivel_medio: Optional[bool] = None
    graduacoes: List[GraduacaoIn] = Field(default_factory=list)
    pos_graduacoes: List[PosGraduacaoIn] = Field(default_factory=list)


# Efetivo – listas auxiliares
class EfetivoCapacitacaoIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    protocolo: Optional[str] = None
    curso: str = Field(min_length=2)
    conclusao_data: Optional[str] = None
    decreto_numero: Optional[str] = None
    resolucao_conjunta: Optional[str] = None
    classe: Optional[str] = None


class EfetivoGitiIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    curso: str = Field(min_length=2)
    conclusao_data: Optional[str] = None
    tipo: Literal["graduacao", "mestrado", "doutorado", "pos"]
    percentual: int  # 10 | 15 | 20

    @field_validator("tipo", mode="before")
    @classmethod
    def _lower_tipo(cls, v):
        if isinstance(v, str):
            v = v.strip().lower()
        return v

    @field_validator("percentual", mode="before")
    @classmethod
    def _coerce_percentual(cls, v):
        if isinstance(v, str):
            v = v.strip()
            if v.isdigit():
                v = int(v)
        if v not in (10, 15, 20):
            raise ValueError("percentual must be 10, 15 or 20")
        return v


class EfetivoOutroCargoIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    funcao_ou_cc: Optional[str] = None
    decreto_nomeacao_numero: Optional[str] = None
    decreto_nomeacao_data: Optional[str] = None
    posse_data: Optional[str] = None
    exercicio_data: Optional[str] = None
    simbolo: Optional[str] = None
    decreto_exoneracao_numero: Optional[str] = None
    decreto_exoneracao_data: Optional[str] = None


class EfetivoIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    decreto_nomeacao_numero: Optional[str] = None
    decreto_nomeacao_data: Optional[str] = None
    posse_data: Optional[str] = None
    exercicio_data: Optional[str] = None
    lotacao_portaria: Optional[str] = None
    cedido_de: Optional[str] = None
    cedido_para: Optional[str] = None
    classe: Optional[str] = None
    estabilidade_data: Optional[str] = None
    estabilidade_protocolo: Optional[str] = None
    estabilidade_resolucao_conjunta: Optional[str] = None
    estabilidade_publicacao_data: Optional[str] = None
    capacitacoes: List[EfetivoCapacitacaoIn] = Field(default_factory=list)
    giti: List[EfetivoGitiIn] = Field(default_factory=list)
    outro_cargo: Optional[EfetivoOutroCargoIn] = None


class ComissionadoIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    decreto_nomeacao_numero: Optional[str] = None
    decreto_nomeacao_data: Optional[str] = None
    posse_data: Optional[str] = None
    exercicio_data: Optional[str] = None
    simbolo: Optional[str] = None
    decreto_exoneracao_numero: Optional[str] = None
    decreto_exoneracao_data: Optional[str] = None
    com_vinculo: Optional[bool] = None
    funcao_exercida: Optional[str] = None


class EstagiarioIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    tce_numero: Optional[str] = None
    tce_ano: Optional[int] = None
    inicio_data: Optional[str] = None
    fim_data: Optional[str] = None
    aditivo_novo_fim_data: Optional[str] = None
    rescisao_data: Optional[str] = None
    # Controles operacionais
    fluxogramas: Optional[str] = None
    frequencia: Optional[str] = None
    pagamento: Optional[str] = None
    vale_transporte: Optional[bool] = None


TipoVinculo = Literal["efetivo", "comissionado", "estagiario"]
StatusVinculo = Literal["ativo", "inativo"]  # employment.status
MotivoInatividade = Literal["exoneracao", "aposentadoria"]


class UserCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    # Núcleo comum
    nome_completo: str = Field(..., min_length=3, max_length=200)
    cpf: str = Field(..., min_length=11, max_length=14)
    rg: Optional[str] = None
    id_funcional: Optional[int] = None
    data_nascimento: Optional[str] = None  # YYYY-MM-DD
    email_principal: Optional[str] = None
    email_institucional: Optional[str] = None
    telefone_principal: Optional[str] = None
    ramal: Optional[str] = None
    endereco: Optional[str] = None
    dependentes_qtde: Optional[int] = Field(default=0, ge=0)
    formacao: Optional[FormacaoIn] = None

    # Vínculo
    tipo_vinculo: TipoVinculo
    status: StatusVinculo = "ativo"
    motivo_inatividade: Optional[MotivoInatividade] = None

    # Unidade Organizacional (opcional; se omitir, usa DEFAULT_ORG_UNIT_CODE)
    org_unit_code: Optional[str] = Field(
        default=None,
        description='code da org unit (ex.: GOV-RH); se omitido, usa default'
    )

    # Específicos
    efetivo: Optional[EfetivoIn] = None
    comissionado: Optional[ComissionadoIn] = None
    estagiario: Optional[EstagiarioIn] = None


class UserUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    # Núcleo (opcionais)
    nome_completo: Optional[str] = Field(default=None, min_length=3, max_length=200)
    cpf: Optional[str] = Field(default=None, min_length=11, max_length=14)
    rg: Optional[str] = None
    id_funcional: Optional[int] = None
    data_nascimento: Optional[str] = None
    email_principal: Optional[str] = None
    email_institucional: Optional[str] = None
    telefone_principal: Optional[str] = None
    ramal: Optional[str] = None
    endereco: Optional[str] = None
    dependentes_qtde: Optional[int] = Field(default=None, ge=0)
    formacao: Optional[FormacaoIn] = None
    # Emprego
    tipo_vinculo: Optional[TipoVinculo] = None
    status: Optional[StatusVinculo] = None
    motivo_inatividade: Optional[MotivoInatividade] = None
    org_unit_code: Optional[str] = None
    # Especializações
    efetivo: Optional[EfetivoIn] = None
    comissionado: Optional[ComissionadoIn] = None
    estagiario: Optional[EstagiarioIn] = None


# ---------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------
@router.get("/ui")
def ui() -> HTMLResponse:
    html = _read_html("ui.html")
    return HTMLResponse(content=html)


@router.get("/ui/search")
@router.get("/ui/search/")
def ui_search(request: Request) -> HTMLResponse:
    """
    UI separada para busca de usuários cadastrados (padrão semelhante ao DFD: /ui/history).
    """
    checker = require_roles_any(*REQUIRED_ROLES)
    checker(request)
    html = _read_html("search.html")
    return HTMLResponse(content=html)


@router.get("/ui/user/{user_id}")
def ui_user_detail(user_id: str, request: Request) -> HTMLResponse:
    """
    UI de detalhe do usuário (renderiza tabela 'completíssima').
    """
    checker = require_roles_any(*REQUIRED_ROLES)
    checker(request)
    html = _read_html("detail.html")
    return HTMLResponse(content=html)


@router.get("/ui/user/{user_id}/edit")
def ui_user_edit(user_id: str, request: Request) -> HTMLResponse:
    """
    UI de edição do usuário.
    """
    checker = require_roles_any(*REQUIRED_ROLES)
    checker(request)
    html = _read_html("detail_edit.html")
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------
# JSON endpoints
# ---------------------------------------------------------------------
@router.get("/schema")
def schema() -> Dict[str, Any]:
    with _pg() as conn, conn.cursor() as cur:
        cur.execute("SELECT code, name FROM org_units WHERE active = TRUE ORDER BY code")
        orgs = [dict(r) for r in (cur.fetchall() or [])]
    return {
        "name": "usuarios",
        "version": "0.1.0",
        "enums": {
            "tipo_vinculo": ["efetivo", "comissionado", "estagiario"],
            "status_vinculo": ["ativo", "inativo"],
            "motivo_inatividade": ["exoneracao", "aposentadoria"],
            "giti_tipo": ["graduacao", "mestrado", "doutorado", "pos"],
            "giti_percentual": [10, 15, 20],
        },
        "org_units": orgs,
        "default_org_unit_code": DEFAULT_ORG_UNIT_CODE,
        "notes": "Cadastro e gestão de usuários corporativos pelo RH (modelo relacional).",
    }


@router.get("/users")
def list_users(
    q: Optional[str] = Query(default=None, description="Busca por nome/email/CPF"),
    tipo_vinculo: Optional[TipoVinculo] = Query(default=None),
    status_vinculo: Optional[StatusVinculo] = Query(default=None),
    org_unit: Optional[str] = Query(default=None, description="code da org unit"),
    limit: int = 500,
    offset: int = 0,
) -> Dict[str, Any]:
    limit = clamp(limit, 1, 200)
    offset = max(0, offset)

    wheres = ["1=1"]
    params: List[Any] = []
    if q:
        only = safe_digits(q)
        if len(only) == 11:
            wheres.append("u.cpf = %s")
            params.append(only)
        else:
            wheres.append("(u.name ILIKE %s OR u.email ILIKE %s)")
            like = f"%{q}%"
            params.extend([like, like])
    if tipo_vinculo:
        wheres.append("e.type = %s")
        params.append(tipo_vinculo)
    if status_vinculo:
        wheres.append("e.status = %s")
        params.append(status_vinculo)
    if org_unit:
        wheres.append("ou.code = %s")
        params.append(org_unit)

    where_sql = " AND ".join(wheres)
    sql = f"""
      SELECT
        u.id::text        AS id,
        u.name            AS nome_completo,
        u.cpf,
        u.email           AS email_principal,
        u.id_funcional    AS id_funcional,
        u.email_institucional,
        u.telefone_principal,
        u.ramal,
        u.endereco,
        u.dependentes_qtde,
        u.formacao_nivel_medio,
        u.status          AS status_usuario,
        e.type            AS tipo_vinculo,
        e.status          AS status_vinculo,
        e.inactivity_reason AS motivo_inatividade,
        ou.code           AS org_code,
        ou.name           AS org_name
      FROM users u
      LEFT JOIN employment e ON e.user_id = u.id AND e.end_date IS NULL
      LEFT JOIN org_units ou ON ou.id = e.org_unit_id
      WHERE {where_sql}
      ORDER BY u.name ASC NULLS LAST
      LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])

    with _pg() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall() or []
        items = []
        for r in rows:
            d = dict(r)
            d["org_unit"] = {"code": d.pop("org_code", None), "name": d.pop("org_name", None)} if d.get("org_code") else None
            items.append(d)
        # total
        cur.execute(
            f"""
            SELECT COUNT(DISTINCT u.id) AS c
            FROM users u
            LEFT JOIN employment e ON e.user_id = u.id AND e.end_date IS NULL
            LEFT JOIN org_units ou ON ou.id = e.org_unit_id
            WHERE {where_sql}
            """,
            params[:-2],
        )
        total = (cur.fetchone() or {}).get("c", 0) or 0

    return {"items": items, "count": len(items), "total": total, "limit": limit, "offset": offset}


@router.get("/users/{user_id}")
def get_user_detail(user_id: str) -> Dict[str, Any]:
    """
    Detalhe 'completíssimo' do usuário.
    - Núcleo (users)
    - Emprego atual (employment + org_units)
      - Especializações (efetivo/comissionado/estagiario) e listas
    - Formação (graduações/pos)
    """
    # Reutiliza a mesma lógica de snapshot completo
    return _snapshot_full(user_id)


@router.post("/users")
def create_user(payload: UserCreateIn, request: Request):
    # normalizações e validações
    cpf_digits = norm_cpf(payload.cpf)
    assert cpf_digits is not None  # norm_cpf já valida

    if payload.status == "inativo" and not payload.motivo_inatividade:
        raise HTTPException(status_code=422, detail="motivo_inatividade é obrigatório quando status = inativo")

    # status do usuário (tabela users) segue padrão do accounts: 'active'|'blocked'|'pending'
    user_status = map_user_status_from_employment(payload.status)

    temp_pin = gen_temp_pin()
    pwd_hash = hasher.hash(temp_pin)

    with _pg() as conn, conn.cursor() as cur:
        # unicidade
        cur.execute("SELECT 1 FROM users WHERE cpf = %s", (cpf_digits,))
        if cur.fetchone():
            return err_json(409, code="conflict", message="CPF já cadastrado.")
        if payload.email_principal:
            cur.execute("SELECT 1 FROM users WHERE email = %s", (payload.email_principal,))
            if cur.fetchone():
                return err_json(409, code="conflict", message="E-mail já cadastrado.")

        # org unit (opcional) — usa default "AGEPAR" se não vier no payload
        desired_code = payload.org_unit_code or DEFAULT_ORG_UNIT_CODE
        cur.execute("SELECT id FROM org_units WHERE code = %s AND active = TRUE", (desired_code,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=500, detail=f'Org Unit padrão "{desired_code}" não encontrada. Verifique as seeds.')
        org_unit_id = row["id"]

        # cria usuário
        cur.execute(
            """
            INSERT INTO users (
              cpf, email, name, password_hash, status, is_superuser, must_change_password,
              rg, id_funcional, data_nascimento, email_institucional, telefone_principal, ramal, endereco,
              dependentes_qtde, formacao_nivel_medio
            )
            VALUES (%s,%s,%s,%s,%s,false,TRUE,
                    %s,%s,%s,%s,%s,%s,%s,
                    %s,%s)
            RETURNING id::text
            """,
            (
                cpf_digits,
                payload.email_principal,
                payload.nome_completo,
                pwd_hash,
                user_status,
                payload.rg,
                payload.id_funcional,
                payload.data_nascimento,
                payload.email_institucional,
                payload.telefone_principal,
                payload.ramal,
                payload.endereco,
                payload.dependentes_qtde or 0,
                (payload.formacao.nivel_medio if payload.formacao and payload.formacao.nivel_medio is not None else False),
            ),
        )
        row = cur.fetchone() or {}
        user_id = row.get("id")
        if not user_id:
            raise HTTPException(status_code=500, detail="Falha ao criar usuário (sem id).")

        # formação (listas)
        if payload.formacao:
            for g in (payload.formacao.graduacoes or []):
                cur.execute(
                    "INSERT INTO user_education_graduacao (user_id, curso, instituicao, conclusao_data) VALUES (%s,%s,%s,%s)",
                    (user_id, g.curso, g.instituicao, g.conclusao_data),
                )
            for p in (payload.formacao.pos_graduacoes or []):
                cur.execute(
                    "INSERT INTO user_education_posgrad (user_id, curso, tipo, instituicao, conclusao_data) VALUES (%s,%s,%s,%s,%s)",
                    (user_id, p.curso, p.tipo, p.instituicao, p.conclusao_data),
                )

        # vínculo base
        cur.execute(
            """
            INSERT INTO employment (user_id, type, status, inactivity_reason, org_unit_id, start_date)
            VALUES (%s, %s, %s, %s, %s, CURRENT_DATE)
            RETURNING id::text
            """,
            (user_id, payload.tipo_vinculo, payload.status, payload.motivo_inatividade, org_unit_id),
        )
        emp_id = (cur.fetchone() or {}).get("id")

        # especialização: EFETIVO
        if payload.tipo_vinculo == "efetivo":
            e = (payload.efetivo.model_dump() if payload.efetivo else {})
            cur.execute(
                """
                INSERT INTO employment_efetivo (
                    employment_id, decreto_nomeacao_numero, decreto_nomeacao_data, posse_data, exercicio_data,
                    lotacao_portaria, cedido_de, cedido_para,
                    classe,
                    estabilidade_data, estabilidade_protocolo, estabilidade_resolucao_conjunta, estabilidade_publicacao_data
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    emp_id,
                    e.get("decreto_nomeacao_numero"),
                    e.get("decreto_nomeacao_data"),
                    e.get("posse_data"),
                    e.get("exercicio_data"),
                    e.get("lotacao_portaria"),
                    e.get("cedido_de"),
                    e.get("cedido_para"),
                    e.get("classe"),
                    e.get("estabilidade_data"),
                    e.get("estabilidade_protocolo"),
                    e.get("estabilidade_resolucao_conjunta"),
                    e.get("estabilidade_publicacao_data"),
                ),
            )
            # listas: capacitações
            for cap in (payload.efetivo.capacitacoes if payload.efetivo else []) or []:
                cur.execute(
                    """
                    INSERT INTO efetivo_capacitacoes
                      (employment_id, protocolo, curso, conclusao_data, decreto_numero, resolucao_conjunta, classe)
                    VALUES (%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        emp_id,
                        cap.protocolo,
                        cap.curso,
                        cap.conclusao_data,
                        cap.decreto_numero,
                        cap.resolucao_conjunta,
                        cap.classe,
                    ),
                )
            # listas: GITI
            for g in (payload.efetivo.giti if payload.efetivo else []) or []:
                cur.execute(
                    """
                    INSERT INTO efetivo_giti
                      (employment_id, curso, conclusao_data, tipo, percentual)
                    VALUES (%s,%s,%s,%s,%s)
                    """,
                    (emp_id, g.curso, g.conclusao_data, g.tipo, int(g.percentual)),
                )
            # outro cargo (opcional)
            oc = payload.efetivo.outro_cargo if payload.efetivo else None
            if oc:
                cur.execute(
                    """
                    INSERT INTO employment_efetivo_outro_cargo
                      (employment_id, funcao_ou_cc, decreto_nomeacao_numero, decreto_nomeacao_data,
                       posse_data, exercicio_data, simbolo, decreto_exoneracao_numero, decreto_exoneracao_data)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        emp_id,
                        oc.funcao_ou_cc,
                        oc.decreto_nomeacao_numero,
                        oc.decreto_nomeacao_data,
                        oc.posse_data,
                        oc.exercicio_data,
                        oc.simbolo,
                        oc.decreto_exoneracao_numero,
                        oc.decreto_exoneracao_data,
                    ),
                )

        # especialização: COMISSIONADO
        elif payload.tipo_vinculo == "comissionado" and payload.comissionado:
            c = payload.comissionado
            cur.execute(
                """
                INSERT INTO employment_comissionado (
                    employment_id, decreto_nomeacao_numero, decreto_nomeacao_data, posse_data, exercicio_data,
                    simbolo, decreto_exoneracao_numero, decreto_exoneracao_data, com_vinculo, funcao_exercida
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    emp_id,
                    c.decreto_nomeacao_numero,
                    c.decreto_nomeacao_data,
                    c.posse_data,
                    c.exercicio_data,
                    c.simbolo,
                    c.decreto_exoneracao_numero,
                    c.decreto_exoneracao_data,
                    c.com_vinculo,
                    c.funcao_exercida,
                ),
            )

        # especialização: ESTAGIÁRIO
        elif payload.tipo_vinculo == "estagiario" and payload.estagiario:
            s = payload.estagiario
            cur.execute(
                """
                INSERT INTO employment_estagiario (
                    employment_id, tce_numero, tce_ano, inicio_data, fim_data,
                    aditivo_novo_fim_data, rescisao_data,
                    fluxogramas, frequencia, pagamento, vale_transporte
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    emp_id,
                    s.tce_numero,
                    s.tce_ano,
                    s.inicio_data,
                    s.fim_data,
                    s.aditivo_novo_fim_data,
                    s.rescisao_data,
                    s.fluxogramas,
                    s.frequencia,
                    s.pagamento,
                    s.vale_transporte,
                ),
            )

        # auditoria + submission (guardar o code efetivamente usado)
        actor = request.session.get("user") or {}
        add_audit("usuarios", "user.create", actor, {"user_id": user_id, "org_unit": desired_code})
        insert_submission(
            _json_safe({
                "kind": "usuarios",
                "version": "0.1.0",
                "actor_cpf": actor.get("cpf"),
                "actor_nome": actor.get("name") or actor.get("nome"),
                "actor_email": actor.get("email"),
                "payload": {
                    "action": "create_user",
                    "user_id": user_id,
                    "cpf": cpf_digits,
                    "email": payload.email_principal,
                    "tipo_vinculo": payload.tipo_vinculo,
                    "status_vinculo": payload.status,
                    "motivo_inatividade": payload.motivo_inatividade,
                    "org_unit": desired_code,
                },
                "status": "done",
                "result": {"user_id": user_id},
                "error": None,
            })
        )

    # devolve PIN (RH comunica ao usuário)
    return {"ok": True, "id": user_id, "temporary_pin": temp_pin}


@router.put("/users/{user_id}")
def update_user(user_id: str, payload: UserUpdateIn, request: Request):
    """
    Atualiza completamente os dados do usuário, emprego atual e especializações.
    Estratégia para listas: 'replace' (apaga e recria quando fornecidas).
    Histórico: diff profundo 'antes vs depois', com paths detalhados.
    """
    # snapshot "antes" para diff completo
    before = _snapshot_full(user_id)
    payload_dict = payload.model_dump(exclude_unset=True)

    with _pg() as conn, conn.cursor() as cur:
        # existência
        cur.execute("SELECT id::text FROM users WHERE id::text = %s", (user_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="user not found")

        # validações básicas
        cpf_digits = None
        if "cpf" in payload_dict:
            cpf_digits = norm_cpf(payload.cpf)
        if cpf_digits:
            cur.execute("SELECT 1 FROM users WHERE cpf = %s AND id::text <> %s", (cpf_digits, user_id))
            if cur.fetchone():
                return err_json(409, code="conflict", message="CPF já cadastrado para outro usuário.")
        if "email_principal" in payload_dict and payload.email_principal:
            cur.execute("SELECT 1 FROM users WHERE email = %s AND id::text <> %s", (payload.email_principal, user_id))
            if cur.fetchone():
                return err_json(409, code="conflict", message="E-mail já cadastrado para outro usuário.")
        if payload.status == "inativo" and payload.motivo_inatividade is None:
            raise HTTPException(status_code=422, detail="motivo_inatividade é obrigatório quando status = inativo")

        # update users (parciais)
        sets: List[str] = []
        params: List[Any] = []

        def add_set(col: str, val: Any):
            sets.append(f"{col} = %s")
            params.append(val)

        if "nome_completo" in payload_dict: add_set("name", payload.nome_completo)
        if cpf_digits is not None: add_set("cpf", cpf_digits)
        if "rg" in payload_dict: add_set("rg", payload.rg)
        if "id_funcional" in payload_dict: add_set("id_funcional", payload.id_funcional)
        if "data_nascimento" in payload_dict: add_set("data_nascimento", payload.data_nascimento)
        if "email_principal" in payload_dict: add_set("email", payload.email_principal)
        if "email_institucional" in payload_dict: add_set("email_institucional", payload.email_institucional)
        if "telefone_principal" in payload_dict: add_set("telefone_principal", payload.telefone_principal)
        if "ramal" in payload_dict: add_set("ramal", payload.ramal)
        if "endereco" in payload_dict: add_set("endereco", payload.endereco)
        if "dependentes_qtde" in payload_dict: add_set("dependentes_qtde", payload.dependentes_qtde)
        if payload.formacao is not None and payload.formacao.nivel_medio is not None:
            add_set("formacao_nivel_medio", bool(payload.formacao.nivel_medio))
        # refletir status do employment no users.status se vier
        if "status" in payload_dict and payload.status is not None:
            add_set("status", map_user_status_from_employment(payload.status))
        if sets:
            cur.execute("UPDATE users SET " + ", ".join(sets) + " WHERE id::text = %s", (*params, user_id))

        # emprego atual
        cur.execute(
            "SELECT id::text, type FROM employment WHERE user_id = %s AND end_date IS NULL ORDER BY start_date DESC LIMIT 1",
            (user_id,),
        )
        erow = cur.fetchone()
        employment_id = (erow or {}).get("id")
        current_type = (erow or {}).get("type")

        # criar emprego se não existir e houver dados do emprego
        if not employment_id and any(k in payload_dict for k in ("tipo_vinculo", "status", "org_unit_code", "motivo_inatividade")):
            desired_code = payload.org_unit_code or DEFAULT_ORG_UNIT_CODE
            cur.execute("SELECT id FROM org_units WHERE code = %s AND active = TRUE", (desired_code,))
            ou = cur.fetchone()
            if not ou:
                raise HTTPException(status_code=400, detail="org_unit_code inválido ou inativo")
            cur.execute(
                """
                INSERT INTO employment (user_id, type, status, inactivity_reason, org_unit_id, start_date)
                VALUES (%s,%s,%s,%s,%s,CURRENT_DATE)
                RETURNING id::text
                """,
                (user_id, payload.tipo_vinculo or "efetivo", payload.status or "ativo", payload.motivo_inatividade, ou["id"]),
            )
            employment_id = (cur.fetchone() or {}).get("id")
            current_type = payload.tipo_vinculo or "efetivo"

        if employment_id:
            # atualizar campos do emprego
            esets: List[str] = []
            eparams: List[Any] = []
            if "tipo_vinculo" in payload_dict:
                esets.append("type = %s"); eparams.append(payload.tipo_vinculo); current_type = payload.tipo_vinculo
            if "status" in payload_dict:
                esets.append("status = %s"); eparams.append(payload.status)
            if "motivo_inatividade" in payload_dict:
                esets.append("inactivity_reason = %s"); eparams.append(payload.motivo_inatividade)
            if "org_unit_code" in payload_dict:
                cur.execute("SELECT id FROM org_units WHERE code = %s AND active = TRUE", (payload.org_unit_code,))
                ou = cur.fetchone()
                if not ou:
                    raise HTTPException(status_code=400, detail="org_unit_code inválido ou inativo")
                esets.append("org_unit_id = %s"); eparams.append(ou["id"])
            if esets:
                cur.execute("UPDATE employment SET " + ", ".join(esets) + " WHERE id::text = %s", (*eparams, employment_id))

            # substituir especializações conforme tipo atual (apenas se payload da especialização foi enviado)
            if current_type == "efetivo" and "efetivo" in payload_dict:
                cur.execute("DELETE FROM employment_efetivo WHERE employment_id = %s", (employment_id,))
                cur.execute("DELETE FROM efetivo_capacitacoes WHERE employment_id = %s", (employment_id,))
                cur.execute("DELETE FROM efetivo_giti WHERE employment_id = %s", (employment_id,))
                cur.execute("DELETE FROM employment_efetivo_outro_cargo WHERE employment_id = %s", (employment_id,))
                e = payload.efetivo.model_dump()
                cur.execute(
                    """
                    INSERT INTO employment_efetivo (
                        employment_id, decreto_nomeacao_numero, decreto_nomeacao_data, posse_data, exercicio_data,
                        lotacao_portaria, cedido_de, cedido_para, classe,
                        estabilidade_data, estabilidade_protocolo, estabilidade_resolucao_conjunta, estabilidade_publicacao_data
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        employment_id,
                        e.get("decreto_nomeacao_numero"),
                        e.get("decreto_nomeacao_data"),
                        e.get("posse_data"),
                        e.get("exercicio_data"),
                        e.get("lotacao_portaria"),
                        e.get("cedido_de"),
                        e.get("cedido_para"),
                        e.get("classe"),
                        e.get("estabilidade_data"),
                        e.get("estabilidade_protocolo"),
                        e.get("estabilidade_resolucao_conjunta"),
                        e.get("estabilidade_publicacao_data"),
                    ),
                )
                for cap in (payload.efetivo.capacitacoes or []):
                    cur.execute(
                        """
                        INSERT INTO efetivo_capacitacoes
                          (employment_id, protocolo, curso, conclusao_data, decreto_numero, resolucao_conjunta, classe)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (employment_id, cap.protocolo, cap.curso, cap.conclusao_data, cap.decreto_numero, cap.resolucao_conjunta, cap.classe),
                    )
                for g in (payload.efetivo.giti or []):
                    cur.execute(
                        "INSERT INTO efetivo_giti (employment_id, curso, conclusao_data, tipo, percentual) VALUES (%s,%s,%s,%s,%s)",
                        (employment_id, g.curso, g.conclusao_data, g.tipo, int(g.percentual)),
                    )
                oc = payload.efetivo.outro_cargo
                if oc:
                    cur.execute(
                        """
                        INSERT INTO employment_efetivo_outro_cargo
                          (employment_id, funcao_ou_cc, decreto_nomeacao_numero, decreto_nomeacao_data,
                           posse_data, exercicio_data, simbolo, decreto_exoneracao_numero, decreto_exoneracao_data)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            employment_id,
                            oc.funcao_ou_cc, oc.decreto_nomeacao_numero, oc.decreto_nomeacao_data,
                            oc.posse_data, oc.exercicio_data, oc.simbolo, oc.decreto_exoneracao_numero, oc.decreto_exoneracao_data,
                        ),
                    )
            elif current_type == "comissionado" and "comissionado" in payload_dict:
                cur.execute("DELETE FROM employment_comissionado WHERE employment_id = %s", (employment_id,))
                c = payload.comissionado
                cur.execute(
                    """
                    INSERT INTO employment_comissionado
                      (employment_id, decreto_nomeacao_numero, decreto_nomeacao_data, posse_data, exercicio_data,
                       simbolo, decreto_exoneracao_numero, decreto_exoneracao_data, com_vinculo, funcao_exercida)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        employment_id,
                        c.decreto_nomeacao_numero, c.decreto_nomeacao_data, c.posse_data, c.exercicio_data,
                        c.simbolo, c.decreto_exoneracao_numero, c.decreto_exoneracao_data, c.com_vinculo, c.funcao_exercida,
                    ),
                )
            elif current_type == "estagiario" and "estagiario" in payload_dict:
                cur.execute("DELETE FROM employment_estagiario WHERE employment_id = %s", (employment_id,))
                s = payload.estagiario
                cur.execute(
                    """
                    INSERT INTO employment_estagiario
                      (employment_id, tce_numero, tce_ano, inicio_data, fim_data,
                       aditivo_novo_fim_data, rescisao_data,
                       fluxogramas, frequencia, pagamento, vale_transporte)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        employment_id,
                        s.tce_numero, s.tce_ano, s.inicio_data, s.fim_data,
                        s.aditivo_novo_fim_data, s.rescisao_data,
                        s.fluxogramas, s.frequencia, s.pagamento, s.vale_transporte,
                    ),
                )

        # formação listas (replace quando fornecidas)
        if "formacao" in payload_dict and payload.formacao is not None:
            cur.execute("DELETE FROM user_education_graduacao WHERE user_id = %s", (user_id,))
            cur.execute("DELETE FROM user_education_posgrad WHERE user_id = %s", (user_id,))
            for g in (payload.formacao.graduacoes or []):
                cur.execute(
                    "INSERT INTO user_education_graduacao (user_id, curso, instituicao, conclusao_data) VALUES (%s,%s,%s,%s)",
                    (user_id, g.curso, g.instituicao, g.conclusao_data),
                )
            for p in (payload.formacao.pos_graduacoes or []):
                cur.execute(
                    "INSERT INTO user_education_posgrad (user_id, curso, tipo, instituicao, conclusao_data) VALUES (%s,%s,%s,%s,%s)",
                    (user_id, p.curso, p.tipo, p.instituicao, p.conclusao_data),
                )

    # === Snapshots antes/depois e diff profundo (fora do bloco para garantir commit visível)
    after = _snapshot_full(user_id)
    changes = _compute_changes(before, after)

    # auditoria + histórico
    actor = request.session.get("user") or {}
    add_audit("usuarios", "user.update", actor, {"user_id": user_id, "changes_count": len(changes)})
    insert_submission(_json_safe({
        "kind": "usuarios",
        "version": "0.1.0",
        "actor_cpf": actor.get("cpf"),
        "actor_nome": actor.get("name") or actor.get("nome"),
        "actor_email": actor.get("email"),
        "payload": {
            "action": "update_user",
            "user_id": user_id,
            "changes": changes,
        },
        "status": "done",
        "result": {"user_id": user_id, "changes": len(changes)},
        "error": None,
    }))

    return {"ok": True, "id": user_id, "changes": len(changes)}

# ===== Normalização, snapshots e diff profundo =======================

def _normalize_bool(v: Any) -> Any:
    if isinstance(v, bool):
        return v
    if v in (None, ""):
        return None
    s = str(v).strip().lower()
    if s in ("true", "1", "sim"):
        return True
    if s in ("false", "0", "nao", "não"):
        return False
    return v

def _norm_date(v: Any) -> Any:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str):
        s = v.strip()
        # aceita "YYYY-MM-DD" ou "YYYY-MM-DDTHH:MM:SS..."
        return s[:10] if len(s) >= 10 else s
    return v

def _norm_value(v: Any) -> Any:
    """Normaliza valores para comparação determinística."""
    if isinstance(v, (datetime, date, time)):
        return _norm_date(v)
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, str)) or v is None:
        return v
    if isinstance(v, dict):
        return {k: _norm_value(vv) for k, vv in v.items()}
    if isinstance(v, list):
        return [_norm_value(x) for x in v]
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, UUID):
        return str(v)
    # fallback
    return v

def _snapshot_full(user_id: str) -> Dict[str, Any]:
    """Snapshot completo do usuário para diff (núcleo, emprego, especializações e listas de educação)."""
    with _pg() as conn, conn.cursor() as cur:
        # Núcleo
        cur.execute(
            """
            SELECT
              u.id::text        AS id,
              u.name            AS nome_completo,
              u.cpf,
              u.rg,
              u.id_funcional,
              u.data_nascimento   AS data_nascimento,
              u.email           AS email_principal,
              u.email_institucional,
              u.telefone_principal,
              u.ramal,
              u.endereco,
              u.dependentes_qtde,
              u.formacao_nivel_medio,
              u.status          AS status_usuario
            FROM users u
            WHERE u.id::text = %s
            """,
            (user_id,),
        )
        urow = cur.fetchone()
        if not urow:
            raise HTTPException(status_code=404, detail="user not found")
        user = dict(urow)
        user["data_nascimento"] = _norm_date(user.get("data_nascimento"))
        user["formacao_nivel_medio"] = _normalize_bool(user.get("formacao_nivel_medio"))

        # Emprego atual
        cur.execute(
            """
            SELECT
              e.id::text AS employment_id,
              e.type     AS tipo_vinculo,
              e.status   AS status_vinculo,
              e.inactivity_reason AS motivo_inatividade,
              e.start_date,
              e.end_date,
              ou.code AS org_code,
              ou.name AS org_name
            FROM employment e
            LEFT JOIN org_units ou ON ou.id = e.org_unit_id
            WHERE e.user_id = %s AND e.end_date IS NULL
            ORDER BY e.start_date DESC
            LIMIT 1
            """,
            (user_id,),
        )
        erow = cur.fetchone()
        employment: Dict[str, Any] | None = None
        if erow:
            e = dict(erow)
            e["start_date"] = _norm_date(e.get("start_date"))
            e["end_date"] = _norm_date(e.get("end_date"))
            e["org_unit"] = {"code": e.pop("org_code", None), "name": e.pop("org_name", None)} if e.get("org_code") else None
            employment = e

            # Especializações
            if e["tipo_vinculo"] == "efetivo":
                cur.execute(
                    """
                    SELECT
                      decreto_nomeacao_numero, decreto_nomeacao_data,
                      posse_data, exercicio_data,
                      lotacao_portaria, cedido_de, cedido_para,
                      classe,
                      estabilidade_data, estabilidade_protocolo,
                      estabilidade_resolucao_conjunta, estabilidade_publicacao_data
                    FROM employment_efetivo
                    WHERE employment_id = %s
                    """,
                    (e["employment_id"],),
                )
                eff = cur.fetchone()
                efetivo = dict(eff) if eff else {}
                # normalizações de datas
                for k in ("decreto_nomeacao_data", "posse_data", "exercicio_data",
                          "estabilidade_data", "estabilidade_publicacao_data"):
                    if k in efetivo:
                        efetivo[k] = _norm_date(efetivo.get(k))

                # Listas
                cur.execute(
                    """
                    SELECT protocolo, curso, conclusao_data, decreto_numero, resolucao_conjunta, classe
                    FROM efetivo_capacitacoes
                    WHERE employment_id = %s
                    ORDER BY id
                    """,
                    (e["employment_id"],),
                )
                caps = [dict(r) for r in (cur.fetchall() or [])]
                for c in caps:
                    c["conclusao_data"] = _norm_date(c.get("conclusao_data"))
                efetivo["capacitacoes"] = caps

                cur.execute(
                    """
                    SELECT curso, conclusao_data, tipo, percentual
                    FROM efetivo_giti
                    WHERE employment_id = %s
                    ORDER BY id
                    """,
                    (e["employment_id"],),
                )
                giti = [dict(r) for r in (cur.fetchall() or [])]
                for g in giti:
                    g["conclusao_data"] = _norm_date(g.get("conclusao_data"))
                efetivo["giti"] = giti

                cur.execute(
                    """
                    SELECT funcao_ou_cc, decreto_nomeacao_numero, decreto_nomeacao_data,
                           posse_data, exercicio_data, simbolo, decreto_exoneracao_numero, decreto_exoneracao_data
                    FROM employment_efetivo_outro_cargo
                    WHERE employment_id = %s
                    LIMIT 1
                    """,
                    (e["employment_id"],),
                )
                oc = cur.fetchone()
                outro = dict(oc) if oc else None
                if outro:
                    for k in ("decreto_nomeacao_data", "posse_data", "exercicio_data", "decreto_exoneracao_data"):
                        outro[k] = _norm_date(outro.get(k))
                efetivo["outro_cargo"] = outro
                employment["efetivo"] = efetivo

            elif e["tipo_vinculo"] == "comissionado":
                cur.execute(
                    """
                    SELECT
                      decreto_nomeacao_numero, decreto_nomeacao_data,
                      posse_data, exercicio_data,
                      simbolo, decreto_exoneracao_numero, decreto_exoneracao_data,
                      com_vinculo, funcao_exercida
                    FROM employment_comissionado
                    WHERE employment_id = %s
                    LIMIT 1
                    """,
                    (e["employment_id"],),
                )
                c = cur.fetchone()
                com = dict(c) if c else {}
                for k in ("decreto_nomeacao_data", "posse_data", "exercicio_data", "decreto_exoneracao_data"):
                    if k in com:
                        com[k] = _norm_date(com.get(k))
                com["com_vinculo"] = _normalize_bool(com.get("com_vinculo"))
                employment["comissionado"] = com

            elif e["tipo_vinculo"] == "estagiario":
                cur.execute(
                    """
                    SELECT
                      tce_numero, tce_ano, inicio_data, fim_data,
                      aditivo_novo_fim_data, limite_alerta_data, rescisao_data,
                      fluxogramas, frequencia, pagamento, vale_transporte
                    FROM employment_estagiario
                    WHERE employment_id = %s
                    LIMIT 1
                    """,
                    (e["employment_id"],),
                )
                s = cur.fetchone()
                est = dict(s) if s else {}
                for k in ("inicio_data", "fim_data", "aditivo_novo_fim_data", "limite_alerta_data", "rescisao_data"):
                    if k in est:
                        est[k] = _norm_date(est.get(k))
                est["vale_transporte"] = _normalize_bool(est.get("vale_transporte"))
                employment["estagiario"] = est

        # Formação
        with _pg() as c2, c2.cursor() as cur2:
            # uso de segunda conexão para garantir consistência de ordering independente de curso principal
            cur2.execute(
                "SELECT curso, instituicao, conclusao_data FROM user_education_graduacao WHERE user_id = %s ORDER BY id",
                (user_id,),
            )
            graduacoes = [dict(r) for r in (cur2.fetchall() or [])]
            for g in graduacoes:
                g["conclusao_data"] = _norm_date(g.get("conclusao_data"))

            cur2.execute(
                "SELECT curso, tipo, instituicao, conclusao_data FROM user_education_posgrad WHERE user_id = %s ORDER BY id",
                (user_id,),
            )
            pos_graduacoes = [dict(r) for r in (cur2.fetchall() or [])]
            for p in pos_graduacoes:
                p["conclusao_data"] = _norm_date(p.get("conclusao_data"))

    return {
        "user": _norm_value(user),
        "employment": _norm_value(employment) if employment else None,
        "educacao": {
            "graduacoes": _norm_value(graduacoes),
            "pos_graduacoes": _norm_value(pos_graduacoes),
        },
    }

def _path_join(base: str, part: str) -> str:
    return f"{base}.{part}" if base else part

def _compute_changes(before: Dict[str, Any], after: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Diff profundo entre snapshots completos. Gera paths para dicts e listas (com índices)."""
    changes: List[Dict[str, Any]] = []

    def _diff(path: str, a: Any, b: Any):
        a = _norm_value(a)
        b = _norm_value(b)

        # igualdade direta
        if a == b:
            return

        # dict
        if isinstance(a, dict) and isinstance(b, dict):
            keys = set(a.keys()) | set(b.keys())
            for k in sorted(keys):
                _diff(_path_join(path, k), a.get(k), b.get(k))
            return

        # list
        if isinstance(a, list) and isinstance(b, list):
            la, lb = len(a), len(b)
            # compara elementos comuns
            for i in range(min(la, lb)):
                _diff(f"{path}[{i}]", a[i], b[i])
            # removidos
            for i in range(min(la, lb), la):
                changes.append({"path": f"{path}[{i}]", "before": a[i], "after": None})
            # adicionados
            for i in range(min(la, lb), lb):
                changes.append({"path": f"{path}[{i}]", "before": None, "after": b[i]})
            return

        # casos simples (tipos diferentes ou valores diferentes)
        changes.append({"path": path, "before": a, "after": b})

    _diff("", before, after)

    # opcional: remover paths raiz vazios ("")
    filtered = [c for c in changes if c.get("path") not in ("",)]
    return filtered


@router.get("/users/{user_id}/history")
def get_user_history(user_id: str, limit: int = 200, offset: int = 0) -> Dict[str, Any]:
    """
    Retorna histórico de eventos (criação/atualizações) do usuário,
    baseado em submissions com kind="usuarios".

    - Busca em lotes para não ficar preso ao limite interno (ex.: 50) do list_submissions_admin.
    - Aplica paginação (limit/offset) apenas após filtrar os eventos do usuário alvo.
    """
    # Limites de resposta desta rota
    limit = clamp(limit, 1, 500)
    offset = max(0, offset)

    # Parâmetros de coleta paginada (teto amplo e lote generoso)
    HISTORY_MAX = 20000   # total máximo de eventos a vasculhar (somados)
    BATCH_SIZE = 1000     # tamanho do lote por consulta

    items_all: List[Dict[str, Any]] = []
    fetched = 0
    ofs = 0

    while fetched < HISTORY_MAX:
        # tamanho solicitado neste passo
        req = min(BATCH_SIZE, HISTORY_MAX - fetched)

        batch = list_submissions_admin(kind="usuarios", limit=req, offset=ofs)
        if not batch:
            break

        fetched += len(batch)
        ofs += len(batch)

        for s in batch:
            p = (s or {}).get("payload") or {}
            if p.get("user_id") != user_id:
                continue
            act = p.get("action")
            if act not in ("create_user", "update_user"):
                continue
            items_all.append({
                "id": s.get("id"),
                "at": s.get("created_at") or s.get("created") or s.get("ts"),
                "action": act,
                "actor": {
                    "cpf": s.get("actor_cpf"),
                    "nome": s.get("actor_nome"),
                    "email": s.get("actor_email"),
                },
                "changes": p.get("changes") or [],  # lista [{path,before,after}] em updates
            })

        # Se o lote veio menor que o requisitado, não há mais páginas
        if len(batch) < req:
            break

    # Ordena (antigos primeiro) e aplica paginação final
    items_all.sort(key=lambda x: (x.get("at") or ""))

    window = items_all[offset: offset + limit]
    return {
        "items": window,
        "count": len(window),
        "total": len(items_all),
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------
# Compat "automations" (submissions)
# ---------------------------------------------------------------------
@router.get("/submissions")
def submissions(limit: int = 500, offset: int = 0) -> Dict[str, Any]:
    # aumenta o teto para consultas administrativas
    limit = clamp(limit, 1, max(500, USUARIOS_HISTORY_BATCH))
    offset = max(0, offset)
    return {"items": list_submissions_admin(kind="usuarios", limit=limit, offset=offset)}


@router.get("/submissions/{submission_id}")
def get_sub(submission_id: str) -> Dict[str, Any]:
    sub = get_submission(submission_id)
    if not sub or sub.get("kind") != "usuarios":
        raise HTTPException(status_code=404, detail="submission not found")
    return sub


@router.post("/submissions/{_submission_id}/download")
def download(_submission_id: str):
    raise HTTPException(status_code=404, detail="sem artefatos para download nesta automação")
