# apps/bff/app/automations/usuarios.py
from __future__ import annotations

import logging
import pathlib
import re
from typing import Any, Dict, List, Optional, Literal
from secrets import choice

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from argon2 import PasswordHasher

from app.auth.rbac import require_roles_any
from app.db import insert_submission, get_submission, list_submissions_admin, add_audit, _pg  # type: ignore

logger = logging.getLogger(__name__)

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


def _read_html(name: str) -> str:
    path = TPL_DIR / name
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        # fallback mínimo para não quebrar preview caso o template ainda não exista
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
    classe_nivel: Optional[int] = Field(default=None, ge=0)
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
    # Guard RBAC (consistente com os endpoints sensíveis)
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
    limit: int = 50,
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
      ORDER BY u.created_at DESC
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
              u.data_nascimento,
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
                      classe, classe_nivel,
                      estabilidade_data, estabilidade_protocolo,
                      estabilidade_resolucao_conjunta, estabilidade_publicacao_data
                    FROM employment_efetivo
                    WHERE employment_id = %s
                    """,
                    (e["employment_id"],),
                )
                eff = cur.fetchone()
                efetivo = dict(eff) if eff else {}

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
                efetivo["capacitacoes"] = [dict(r) for r in (cur.fetchall() or [])]

                cur.execute(
                    """
                    SELECT curso, conclusao_data, tipo, percentual
                    FROM efetivo_giti
                    WHERE employment_id = %s
                    ORDER BY id
                    """,
                    (e["employment_id"],),
                )
                efetivo["giti"] = [dict(r) for r in (cur.fetchall() or [])]

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
                efetivo["outro_cargo"] = dict(oc) if oc else None
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
                employment["comissionado"] = dict(c) if c else {}

            elif e["tipo_vinculo"] == "estagiario":
                cur.execute(
                    """
                    SELECT
                      tce_numero, tce_ano, inicio_data, fim_data,
                      aditivo_novo_fim_data, rescisao_data,
                      fluxogramas, frequencia, pagamento, vale_transporte
                    FROM employment_estagiario
                    WHERE employment_id = %s
                    LIMIT 1
                    """,
                    (e["employment_id"],),
                )
                s = cur.fetchone()
                employment["estagiario"] = dict(s) if s else {}

        # Formação
        cur.execute(
            "SELECT curso, instituicao, conclusao_data FROM user_education_graduacao WHERE user_id = %s ORDER BY id",
            (user_id,),
        )
        graduacoes = [dict(r) for r in (cur.fetchall() or [])]
        cur.execute(
            "SELECT curso, tipo, instituicao, conclusao_data FROM user_education_posgrad WHERE user_id = %s ORDER BY id",
            (user_id,),
        )
        pos_graduacoes = [dict(r) for r in (cur.fetchall() or [])]

    return {
        "user": user,
        "employment": employment,
        "educacao": {
            "graduacoes": graduacoes,
            "pos_graduacoes": pos_graduacoes,
        },
    }


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
            # isso só ocorre se a seed da raiz não existir
            raise HTTPException(status_code=500, detail=f'Org Unit padrão "{desired_code}" não encontrada. Verifique as seeds.')
        org_unit_id = row["id"]

        # cria usuário (novas colunas normalizadas)
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
                    classe, classe_nivel,
                    estabilidade_data, estabilidade_protocolo, estabilidade_resolucao_conjunta, estabilidade_publicacao_data
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                    e.get("classe_nivel"),
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
                    employment_id, tce_numero, tce_ano, inicio_data, fim_data, aditivo_novo_fim_data, rescisao_data,
                    fluxogramas, frequencia, pagamento, vale_transporte
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
            {
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
            }
        )

    # devolve PIN (RH comunica ao usuário)
    return {"ok": True, "id": user_id, "temporary_pin": temp_pin}


# ---------------------------------------------------------------------
# Compat "automations" (submissions)
# ---------------------------------------------------------------------
@router.get("/submissions")
def submissions(limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    limit = clamp(limit, 1, 200)
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
