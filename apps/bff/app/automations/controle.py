# apps/bff/app/automations/controle.py
"""
Painel de Controle (somente leitura) — Portal AGEPAR

Propósito
---------
Fornece uma UI simples e endpoints para consulta e exportação de:
- Eventos de auditoria de automações (automation_audits).
- Submissões realizadas (submissions).

Segurança
---------
- Todos os endpoints são protegidos por RBAC e exigem **qualquer um** dos seguintes:
  `coordenador`, `admin` **ou** usuário com `is_superuser == true`.

Compatibilidade
---------------
- Integra com a camada `app.db` e tolera variações de assinatura mais antigas
  (ex.: `list_audits()` sem parâmetros), mantendo *fallbacks* quando necessário.

Endpoints
---------
UI
- GET /api/automations/controle/ui

Metadados
- GET /api/automations/controle/schema

Auditoria
- GET /api/automations/controle/actions           (listar ações distintas)
- GET /api/automations/controle/kinds             (listar alvos/kinds distintos)
- GET /api/automations/controle/audits            (lista paginada)
- GET /api/automations/controle/audits.csv        (exportação CSV)

Submissões
- GET /api/automations/controle/submissions       (lista paginada)
- GET /api/automations/controle/submissions/{id}  (detalhe)

Não suportado (somente leitura)
- POST /api/automations/controle/submit
- POST /api/automations/controle/submissions/{id}/download
"""

from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeVar, Generic

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from app.auth.rbac import require_roles_any  # segue utilizado em alguns pontos
from app import db as db

logger = logging.getLogger(__name__)

def require_admin_coord_or_superuser(request: Request) -> Dict[str, Any]:
    """
    Autoriza se o usuário for superuser OU tiver 'admin' OU 'coordenador'.
    """
    user = (getattr(request, "session", {}) or {}).get("user") or {}
    roles = set((user.get("roles") or []))
    if user.get("is_superuser") is True or "admin" in roles or "coordenador" in roles:
        return user
    raise HTTPException(status_code=403, detail="forbidden")

router = APIRouter(
    prefix="/api/automations/controle",
    tags=["automations", "controle"],
    dependencies=[Depends(require_admin_coord_or_superuser)],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


class AuditOut(BaseModel):
    """
    Modelo de saída para eventos de auditoria exibidos na UI.

    Campos
    ------
    id : Optional[int]
    ts : Optional[datetime]
        Timestamp do evento (campo `at` ou `ts` da origem).
    user_id : Optional[str]
    username : Optional[str]
        Nome/identificador amigável do ator.
    action : Optional[str]
        Ação realizada (ex.: completed, running, submitted, failed, download).
    target_kind : Optional[str]
        Automação de origem (kind) ou alvo do evento.
    target_id : Optional[str]
        Identificador do alvo (ex.: submission id).
    ip : Optional[str]
    user_agent : Optional[str]
    extra : Optional[Dict[str, Any]]
        Metadados variados (normalizados como dict).

    Campos derivados para a UI
    --------------------------
    protocolo : Optional[str]
        Número padrão do processo, quando detectável.
    alvo : Optional[str]
        Kind normalizado (ex.: dfd, ferias).
    filename : Optional[str]
        Nome de arquivo inferido quando aplicável.
    status : Optional[str]
        Status normalizado para apresentação.
    download_url : Optional[str]
        URL de download na automação de origem (quando inferível).
    submission_url : Optional[str]
        URL de detalhes da submissão **no painel de controle** (read-only).
    origin_submission_url : Optional[str]
        URL de detalhes da submissão na automação de origem (quando inferível).
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    id: Optional[int] = None
    ts: Optional[datetime] = Field(default=None, description="Timestamp do evento")
    user_id: Optional[str] = None
    username: Optional[str] = None
    action: Optional[str] = None
    target_kind: Optional[str] = None
    target_id: Optional[str] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None
    protocolo: Optional[str] = None
    alvo: Optional[str] = None
    filename: Optional[str] = None
    status: Optional[str] = None
    download_url: Optional[str] = None
    submission_url: Optional[str] = None
    origin_submission_url: Optional[str] = None


class SubmissionOut(BaseModel):
    """
    Modelo de saída para submissões listadas/visualizadas no painel.

    Campos
    ------
    id, kind, status, user_id, username, created_at, updated_at, payload, result, error
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    id: Optional[str] = None
    kind: Optional[str] = None
    status: Optional[str] = None
    user_id: Optional[str] = None
    username: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    payload: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[Any] = None


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """
    Envelope de paginação genérico.

    Campos
    ------
    count : int
        Total de itens após filtro/paginação no servidor.
    items : List[T]
        Página de resultados.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    count: int
    items: List[T]


@router.get("/ui", response_class=HTMLResponse)
def get_ui(request: Request):
    """
    Renderiza a UI HTML principal do painel (carregada via iframe pelo host).
    """
    return templates.TemplateResponse("controle/ui.html", {"request": request})


@router.get("/schema")
def get_schema():
    """
    Retorna metadados informativos sobre filtros/limites aceitos pelos endpoints.
    """
    return {
        "filters": {
            "kind": {"type": "string", "description": "Opcional: filtra por automação de origem (alvo)"},
            "username": {"type": "string"},
            "action": {"type": "string"},
            "since": {"type": "datetime"},
            "until": {"type": "datetime"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
        },
        "notes": (
            "Painel de controle é somente leitura. "
            "Downloads devem ser feitos na automação de origem; a ação 'ver' usa o próprio Controle."
        ),
    }


def _filter_dates(
    items: List[Dict[str, Any]],
    since: Optional[datetime],
    until: Optional[datetime],
    key_candidates=("ts", "created_at", "updated_at"),
):
    """
    Filtra uma lista de registros por intervalo temporal, tentando múltiplas chaves de data.

    Regras
    ------
    - Aceita valores `datetime` ou strings ISO (com suporte a 'Z').
    - Inclui apenas itens com datas entre `since` e `until` (se informados).
    """
    def pick_dt(row):
        for k in key_candidates:
            v = row.get(k)
            if isinstance(v, str):
                try:
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except Exception:
                    continue
            if isinstance(v, datetime):
                return v
        return None

    out = []
    for it in items:
        dt = pick_dt(it)
        if since and dt and dt < since:
            continue
        if until and dt and dt > until:
            continue
        out.append(it)
    return out


def _to_obj(x: Any) -> Dict[str, Any]:
    """
    Converte `x` em `dict`, aceitando `bytes`, `str` (JSON) ou já `dict`.
    Retorna `{}` quando não for possível converter.
    """
    if x is None:
        return {}
    if isinstance(x, dict):
        return x
    if isinstance(x, (bytes, bytearray)):
        try:
            return json.loads(x.decode("utf-8"))
        except Exception:
            return {}
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return {}
    return {}


def _digits(s: Optional[str]) -> str:
    """
    Mantém apenas dígitos de uma string (útil para busca por CPF).
    """
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def _status_label(action: Optional[str], status: Optional[str]) -> str:
    """
    Normaliza o status exibido na UI a partir de `action` (preferencial) e `status`.

    Mapeamentos
    -----------
    - Ações conhecidas: {completed,running,submitted,failed,download}
    - Status → rótulos: done/ok/success→completed; processing/in_progress→running;
      queued/pending→submitted; error/failed/timeout→failed.
    """
    def norm(x: Optional[str]) -> str:
        return str(x or "").strip().lower()

    a = norm(action)
    s = norm(status)

    known = {"completed", "running", "submitted", "failed", "download", "deleted"}
    if a in known:
        return a

    map_status = {
        "done": "completed",
        "ok": "completed",
        "success": "completed",
        "processing": "running",
        "in_progress": "running",
        "queued": "submitted",
        "pending": "submitted",
        "error": "failed",
        "failed": "failed",
        "timeout": "failed",
    }
    if s in map_status:
        return map_status[s]

    return a or s or ""


def _sid_from_audit_row(row: Dict[str, Any]) -> Optional[str]:
    """
    Tenta extrair o submission id (sid) de diferentes campos usuais do audit.
    """
    extra = row.get("extra") or {}
    return (
        (extra.get("sid") if isinstance(extra, dict) else None)
        or (extra.get("submissionId") if isinstance(extra, dict) else None)
        or (extra.get("id") if isinstance(extra, dict) else None)
        or row.get("target_id")
        or None
    )


def _guess_filename(payload: Dict[str, Any], result: Dict[str, Any], extra: Dict[str, Any]) -> str:
    """
    Heurística para descobrir um nome de arquivo:
    - Procura chaves `filename*`.
    - Procura strings com extensões comuns (.pdf, .docx, .xlsx, .zip).
    """
    def first_filename(d: Dict[str, Any]) -> Optional[str]:
        if not isinstance(d, dict):
            return None
        for k, v in d.items():
            ks = str(k).lower()
            if ks.startswith("filename") and isinstance(v, str) and v.strip():
                return v.strip()
        for _, v in d.items():
            if isinstance(v, str) and any(v.lower().endswith(ext) for ext in [".pdf", ".docx", ".xlsx", ".zip"]):
                return v.strip()
        return None

    return first_filename(result) or first_filename(extra) or first_filename(payload) or ""


def _guess_protocolo(payload: Dict[str, Any], result: Dict[str, Any], extra: Dict[str, Any]) -> str:
    """
    Heurística para descobrir o número de protocolo/processo a partir de chaves comuns.
    """
    def first_proto(d: Dict[str, Any]) -> Optional[str]:
        if not isinstance(d, dict):
            return None
        candidates = [
            "protocolo", "processo", "numero_processo", "n_processo", "num_processo",
            "process_number", "protocol", "protocol_number", "protocolo_alvo",
            "processo_alvo", "protocolo_numero",
        ]
        for k in candidates:
            v = d.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        v = d.get("target_id")
        if isinstance(v, str) and v.strip():
            return v.strip()
        return None

    return first_proto(result) or first_proto(payload) or first_proto(extra) or ""


def _normalize_kind(kind: Optional[str]) -> Optional[str]:
    """
    Normaliza um `kind` removendo o prefixo `automations/` quando presente.
    """
    if not kind:
        return None
    k = str(kind).strip().lower()
    if k.startswith("automations/"):
        k = k.split("/", 1)[1]
    return k or None


def _enrich_with_submission(rows: List[Dict[str, Any]]) -> None:
    """
    Enriquecimento *in-place* dos registros de auditoria com dados da submissão:
    - `alvo` (kind normalizado), `protocolo`, `filename`, `status`
    - `download_url`, `submission_url` (controle) e `origin_submission_url` quando inferíveis.
    """
    for it in rows:
        extra = it.get("extra") or {}
        sid = _sid_from_audit_row(it)
        sub = None
        if sid:
            try:
                sub = db.get_submission(sid)
            except Exception:
                sub = None

        payload = _to_obj(sub.get("payload")) if sub else {}
        result = _to_obj(sub.get("result")) if sub else {}
        extra_obj = extra if isinstance(extra, dict) else {}

        kind = (
            it.get("target_kind")
            or extra_obj.get("kind")
            or (sub.get("kind") if sub else None)
        )
        alvo = _normalize_kind(kind)
        protocolo = _guess_protocolo(payload, result, extra_obj)
        filename = it.get("filename") or extra_obj.get("filename") or _guess_filename(payload, result, extra_obj)
        raw_action = it.get("action")
        raw_status = (sub.get("status") if sub else None) or it.get("status")
        status = _status_label(raw_action, raw_status)

        download_url = None
        submission_url = None
        origin_submission_url = None
        if alvo and sid:
            download_url = f"/api/automations/{alvo}/submissions/{sid}/download"
            submission_url = f"/api/automations/controle/submissions/{sid}"
            origin_submission_url = f"/api/automations/{alvo}/submissions/{sid}"

        it["alvo"] = alvo or ""
        it["protocolo"] = protocolo or ""
        it["filename"] = filename or ""
        it["status"] = status or ""
        it["download_url"] = download_url
        it["submission_url"] = submission_url
        it["origin_submission_url"] = origin_submission_url
        it["extra"] = extra_obj


@router.get("/actions")
def list_actions(kind: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    """
    Lista ações distintas registradas em auditoria, com filtro opcional por `kind`.

    Observação
    ----------
    Aceita `kind` com ou sem prefixo `automations/`; a comparação é feita após normalização.
    """
    try:
        kind_norm = _normalize_kind(kind)
        try:
            rows = db.list_audits(limit=2000, offset=0)
        except TypeError:
            rows = db.list_audits()

        seen = set()
        for r in rows:
            a = (r.get("action") or "").strip()
            if not a:
                continue
            if kind_norm:
                meta = r.get("meta") or r.get("extra") or {}
                rk_raw = r.get("kind") or r.get("target_kind") or (meta.get("kind") if isinstance(meta, dict) else None)
                rk = _normalize_kind(rk_raw)
                if rk != kind_norm:
                    continue
            seen.add(a)
        items = sorted(seen)
        return {"items": items}
    except Exception as e:
        logger.exception("erro ao listar actions")
        raise HTTPException(status_code=500, detail=f"erro ao listar actions: {e}")


@router.get("/kinds")
def list_kinds() -> Dict[str, Any]:
    """
    Lista os kinds/alvos distintos (normalizados) presentes nos registros de auditoria.
    """
    try:
        try:
            rows = db.list_audits(limit=3000, offset=0)
        except TypeError:
            rows = db.list_audits()
        seen = set()
        for r in rows:
            meta = r.get("meta") or r.get("extra") or {}
            rk_raw = r.get("kind") or r.get("target_kind") or (meta.get("kind") if isinstance(meta, dict) else None)
            rk = _normalize_kind(rk_raw)
            if rk:
                seen.add(rk)
        return {"items": sorted(seen)}
    except Exception as e:
        logger.exception("erro ao listar kinds")
        raise HTTPException(status_code=500, detail=f"erro ao listar kinds: {e}")


@router.get("/audits", response_model=Page[AuditOut])
def list_audits_api(
    kind: Optional[str] = Query(default=None),
    username: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    since: Optional[datetime] = Query(default=None),
    until: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """
    Lista eventos de auditoria com filtros e paginação.

    Filtros
    -------
    - `kind` (normalizado), `username` (substring ou CPF apenas dígitos), `action` (substring),
      intervalo temporal (`since`, `until`).
    """
    try:
        try:
            raw = db.list_audits(kind=kind, limit=limit + offset) if kind is not None else db.list_audits(limit=limit + offset)
        except TypeError:
            raw = db.list_audits()

        items: List[Dict[str, Any]] = []
        for r in raw:
            items.append({
                "id": r.get("id"),
                "ts": r.get("at") or r.get("ts"),
                "username": r.get("actor_nome") or r.get("actor_cpf") or r.get("actor_email") or r.get("username"),
                "actor_nome": r.get("actor_nome"),
                "actor_cpf": r.get("actor_cpf"),
                "actor_email": r.get("actor_email"),
                "action": r.get("action"),
                "target_kind": r.get("kind") or r.get("target_kind"),
                "target_id": r.get("target_id"),
                "ip": r.get("ip"),
                "user_agent": r.get("user_agent"),
                "extra": r.get("meta") or r.get("extra") or {},
            })

        def match(it: Dict[str, Any]) -> bool:
            if username:
                term = (username or "").strip().lower()
                term_digits = _digits(username)

                hay = " ".join([
                    str(it.get("username") or ""),
                    str(it.get("actor_nome") or ""),
                    str(it.get("actor_email") or ""),
                ]).lower()

                if term_digits:
                    cpf_digits = _digits(it.get("actor_cpf"))
                    if term_digits not in cpf_digits and term not in hay:
                        return False
                else:
                    if term not in hay:
                        return False

            if action:
                a = it.get("action") or ""
                if action.lower() not in str(a).lower():
                    return False
            if kind:
                kind_norm = _normalize_kind(kind)
                tk_norm = _normalize_kind(it.get("target_kind"))
                ek = (it.get("extra") or {})
                ek_norm = _normalize_kind(ek.get("kind") if isinstance(ek, dict) else None)
                if tk_norm != kind_norm and ek_norm != kind_norm:
                    return False
            return True

        filtered = [it for it in items if match(it)]
        filtered = _filter_dates(filtered, since, until)

        sliced = filtered[offset: offset + limit]
        _enrich_with_submission(sliced)

        return {"count": len(filtered), "items": sliced}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro ao listar audits")
        raise HTTPException(status_code=500, detail=f"erro ao listar audits: {e}")


@router.get("/audits.csv")
def list_audits_csv(
    kind: Optional[str] = Query(default=None),
    username: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    since: Optional[datetime] = Query(default=None),
    until: Optional[datetime] = Query(default=None),
    limit: int = Query(default=1000, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
):
    """
    Exporta eventos de auditoria em CSV respeitando os mesmos filtros do endpoint JSON.
    """
    page = list_audits_api(
        kind=kind,
        username=username,
        action=action,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "ts", "username", "action", "target_kind", "target_id", "ip", "user_agent", "extra"]
    )
    for r in page["items"]:
        writer.writerow(
            [
                r.get("id", ""),
                r.get("ts", ""),
                r.get("username", ""),
                r.get("action", ""),
                r.get("target_kind", ""),
                r.get("target_id", ""),
                r.get("ip", ""),
                r.get("user_agent", ""),
                json.dumps(r.get("extra") or {}, ensure_ascii=False),
            ]
        )
    data = buf.getvalue().encode("utf-8")
    headers = {"Content-Disposition": 'attachment; filename="audits.csv"'}
    return StreamingResponse(
        io.BytesIO(data), media_type="text/csv; charset=utf-8", headers=headers
    )


@router.get("/submissions", response_model=Page[SubmissionOut])
def list_submissions_api(
    kind: Optional[str] = Query(default=None),
    username: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    since: Optional[datetime] = Query(default=None),
    until: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """
    Lista submissões com filtros por `kind`, `username`, `status` e intervalo temporal.
    """
    try:
        try:
            items = db.list_submissions_admin(
                kind=kind, username=username, status=status, limit=limit + offset, offset=0
            )
        except AttributeError:
            raise HTTPException(
                status_code=500,
                detail="list_submissions_admin() não disponível na camada de banco de dados; implemente no módulo de DB do BFF para habilitar o painel de controle.",
            )

        norm: List[Dict[str, Any]] = []
        for r in items:
            result_obj = _to_obj(r.get("result"))
            logical_status = r.get("status")
            if isinstance(result_obj, dict):
                soft_meta = result_obj.get("_soft_delete") or {}
                if isinstance(soft_meta, dict) and soft_meta.get("deleted"):
                    logical_status = "deleted"
                else:
                    result_status = (result_obj.get("status") or "").strip()
                    if result_status:
                        logical_status = result_status

            norm.append({
                "id": r.get("id"),
                "kind": r.get("kind"),
                "status": logical_status,
                "username": r.get("actor_nome") or r.get("actor_cpf") or r.get("actor_email") or r.get("username"),
                "user_id": r.get("actor_cpf") or r.get("user_id"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
                "payload": r.get("payload") or {},
                "result": result_obj,
                "error": r.get("error"),
            })

        norm = _filter_dates(norm, since, until, key_candidates=("created_at", "updated_at", "ts"))
        sliced = norm[offset: offset + limit]
        return {"count": len(norm), "items": sliced}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro ao listar submissions")
        raise HTTPException(status_code=500, detail=f"erro ao listar submissions: {e}")


@router.get("/submissions/{sid}", response_model=SubmissionOut)
def get_submission_api(sid: str):
    """
    Recupera os detalhes de uma submissão específica pelo seu identificador.
    """
    try:
        sub = db.get_submission(sid)
        if not sub:
            raise HTTPException(status_code=404, detail=f"submission {sid} não encontrada")

        result_obj = _to_obj(sub.get("result"))
        logical_status = sub.get("status")
        if isinstance(result_obj, dict):
            soft_meta = result_obj.get("_soft_delete") or {}
            if isinstance(soft_meta, dict) and soft_meta.get("deleted"):
                logical_status = "deleted"
            else:
                result_status = (result_obj.get("status") or "").strip()
                if result_status:
                    logical_status = result_status

        return {
            "id": sub.get("id"),
            "kind": sub.get("kind"),
            "status": logical_status,
            "username": sub.get("actor_nome") or sub.get("actor_cpf") or sub.get("actor_email") or sub.get("username"),
            "user_id": sub.get("actor_cpf") or sub.get("user_id"),
            "created_at": sub.get("created_at"),
            "updated_at": sub.get("updated_at"),
            "payload": sub.get("payload") or {},
            "result": result_obj,
            "error": sub.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro ao buscar submission %s", sid)
        raise HTTPException(status_code=500, detail=f"erro ao buscar submission: {e}")


@router.post("/submit")
def submit_not_supported():
    """
    Endpoint sentinela: o painel é somente leitura.
    """
    raise HTTPException(
        status_code=409,
        detail="controle é somente leitura; use a automação de origem para submeter.",
    )


@router.post("/submissions/{sid}/download")
def download_not_supported(sid: str):
    """
    Endpoint sentinela: downloads devem ser feitos na automação de origem.
    """
    raise HTTPException(
        status_code=409,
        detail=(
            "download deve ser feito na automação de origem "
            "(ex.: /api/automations/{kind}/submissions/{id}/download)."
        ),
    )
