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

from app.auth.rbac import require_roles_any
from app import db as db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/automations/controle",
    tags=["automations", "controle"],
    # exige qualquer um dos papéis: coordenador OU admin
    dependencies=[Depends(require_roles_any("coordenador", "admin"))],
)

# Templates (usa pasta local: apps/bff/app/automations/templates)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# --------------------------
# Pydantic Models (v2)
# --------------------------
class AuditOut(BaseModel):
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
    # ---- Campos para a UI enxuta ----
    protocolo: Optional[str] = None   # número padrão do processo
    alvo: Optional[str] = None        # automação/processo (ex.: dfd, ferias, ...)
    filename: Optional[str] = None
    status: Optional[str] = None
    download_url: Optional[str] = None
    submission_url: Optional[str] = None


class SubmissionOut(BaseModel):
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
    error: Optional[Any] = None  # TEXT no banco; pode ser string ou json


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    count: int
    items: List[T]


# --------------------------
# UI
# --------------------------
@router.get("/ui", response_class=HTMLResponse)
def get_ui(request: Request):
    """
    UI HTML servida por template (iframe).
    """
    return templates.TemplateResponse("controle/ui.html", {"request": request})


# --------------------------
# Schema (informativo)
# --------------------------
@router.get("/schema")
def get_schema():
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
        "notes": "Painel de controle é somente leitura. Baixes/ver ações na automação de origem.",
    }


# --------------------------
# Helpers
# --------------------------
def _filter_dates(
    items: List[Dict[str, Any]],
    since: Optional[datetime],
    until: Optional[datetime],
    key_candidates=("ts", "created_at", "updated_at"),
):
    def pick_dt(row):
        for k in key_candidates:
            v = row.get(k)
            if isinstance(v, str):
                try:
                    # aceita ISO com 'Z'
                    return datetime.fromisoformat(v.replace("Z", "+00:00"))
                except Exception:
                    continue
            if isinstance(v, datetime):
                return v
        return None

    out = []
    for it in items:
        dt = pick_dt(it)  # pode ser None
        if since and dt and dt < since:
            continue
        if until and dt and dt > until:
            continue
        out.append(it)
    return out


def _to_obj(x: Any) -> Dict[str, Any]:
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
    return "".join(ch for ch in str(s or "") if ch.isdigit())


def _status_label(action: Optional[str], status: Optional[str]) -> str:
    """
    Normaliza o status exibido na UI.
    - Prioriza 'action' do audit quando existir (completed, running, submitted, failed, download)
    - Mapeia status da submission para os rótulos antigos.
    """
    def norm(x: Optional[str]) -> str:
        return str(x or "").strip().lower()

    a = norm(action)
    s = norm(status)

    known = {"completed", "running", "submitted", "failed", "download"}
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
    Tenta descobrir um nome de arquivo de forma genérica.
    Procura por chaves filename*, ou strings terminando em extensões comuns.
    """
    def first_filename(d: Dict[str, Any]) -> Optional[str]:
        if not isinstance(d, dict):
            return None
        # chaves filename* mais comuns
        for k, v in d.items():
            ks = str(k).lower()
            if ks.startswith("filename") and isinstance(v, str) and v.strip():
                return v.strip()
        # scan simples por extensões
        for _, v in d.items():
            if isinstance(v, str) and any(v.lower().endswith(ext) for ext in [".pdf", ".docx", ".xlsx", ".zip"]):
                return v.strip()
        return None

    return first_filename(result) or first_filename(extra) or first_filename(payload) or ""


def _guess_protocolo(payload: Dict[str, Any], result: Dict[str, Any], extra: Dict[str, Any]) -> str:
    """
    Descobre o número padrão de processo (protocolo) salvo nas telas.
    Heurística: checa chaves usuais em result/payload/extra.
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
        # às vezes vem dentro de extra.target_id mas é um protocolo
        v = d.get("target_id")
        if isinstance(v, str) and v.strip():
            return v.strip()
        return None

    return first_proto(result) or first_proto(payload) or first_proto(extra) or ""


def _normalize_kind(kind: Optional[str]) -> Optional[str]:
    if not kind:
        return None
    k = str(kind).strip().lower()
    if k.startswith("automations/"):
        k = k.split("/", 1)[1]
    return k or None


def _enrich_with_submission(rows: List[Dict[str, Any]]) -> None:
    """
    Enriquecer in-place de forma genérica:
    - alvo: kind normalizado (dfd, ferias, ...)
    - protocolo: número de processo armazenado
    - filename/status
    - URLs de ação (download/submission) quando (kind,sid) forem conhecidos
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

        # alvo (kind)
        kind = (
            it.get("target_kind")
            or extra_obj.get("kind")
            or (sub.get("kind") if sub else None)
        )
        alvo = _normalize_kind(kind)

        # protocolo
        protocolo = _guess_protocolo(payload, result, extra_obj)

        # filename e status
        filename = it.get("filename") or extra_obj.get("filename") or _guess_filename(payload, result, extra_obj)
        raw_action = it.get("action")
        raw_status = (sub.get("status") if sub else None) or it.get("status")
        status = _status_label(raw_action, raw_status)

        # URLs de apoio
        download_url = None
        submission_url = None
        if alvo and sid:
            download_url = f"/api/automations/{alvo}/submissions/{sid}/download"
            submission_url = f"/api/automations/{alvo}/submissions/{sid}"

        it["alvo"] = alvo or ""
        it["protocolo"] = protocolo or ""
        it["filename"] = filename or ""
        it["status"] = status or ""
        it["download_url"] = download_url
        it["submission_url"] = submission_url
        it["extra"] = extra_obj


# --------------------------
# Endpoints auxiliares (ações distintas)
# --------------------------
@router.get("/actions")
def list_actions(kind: Optional[str] = Query(default=None)) -> Dict[str, Any]:
    """
    Retorna a lista de ações distintas registradas em automation_audits.
    Opcionalmente filtra por kind.
    """
    try:
        kind_norm = _normalize_kind(kind)
        try:
            # Busca ampla (limit maior para cobrir variedade); filtro por kind será aplicado abaixo com normalização.
            rows = db.list_audits(limit=2000, offset=0)
        except TypeError:
            # assinatura antiga (sem params) — faz fallback
            rows = db.list_audits()

        seen = set()
        for r in rows:
            a = (r.get("action") or "").strip()
            if not a:
                continue
            if kind_norm:
                # normaliza origem do kind do registro: r.kind, r.target_kind, meta.kind
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
    Retorna a lista de kinds/alvos distintos (normalizados) presentes nos audits.
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


# --------------------------
# Endpoints de auditoria
# --------------------------
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
    Lista eventos de auditoria com filtros simples e paginação.
    """
    try:
        # Carrega eventos crus do DB (automation_audits)
        try:
            raw = db.list_audits(kind=kind, limit=limit + offset) if kind is not None else db.list_audits(limit=limit + offset)
        except TypeError:
            # assinatura sem limit/kind
            raw = db.list_audits()

        # Normaliza para o contrato AuditOut / UI
        items: List[Dict[str, Any]] = []
        for r in raw:
            items.append({
                "id": r.get("id"),
                "ts": r.get("at") or r.get("ts"),
                "username": r.get("actor_nome") or r.get("actor_cpf") or r.get("actor_email") or r.get("username"),
                # ↓↓↓ PRESERVAR CAMPOS ORIGINAIS PARA FILTRO
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

        # Filtros adicionais (username/action) + datas
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
                    # tenta bater por CPF (apenas dígitos)
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

        # paginação antes do enriquecimento para evitar N consultas desnecessárias
        sliced = filtered[offset: offset + limit]

        # Enriquecer com dados da submission (protocolo/alvo/filename/status/URLs)
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
    Exporta os eventos de auditoria em CSV respeitando os filtros.
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
    # page aqui é um dict {"count": int, "items": [...]}
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


# --------------------------
# Endpoints de submissões (consulta)
# --------------------------
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
    Lista submissões (genérico) com filtros.
    """
    try:
        # Usa o método admin (não exige actor_*), aplicando filtros server-side
        try:
            items = db.list_submissions_admin(
                kind=kind, username=username, status=status, limit=limit + offset, offset=0
            )
        except AttributeError:
            # Se a função ainda não existir, sinaliza claramente
            raise HTTPException(
                status_code=500,
                detail="list_submissions_admin() não disponível na camada de banco de dados; implemente no módulo de DB do BFF para habilitar o painel de controle.",
            )

        # Normaliza campos para o contrato SubmissionOut/UI
        norm: List[Dict[str, Any]] = []
        for r in items:
            norm.append({
                "id": r.get("id"),
                "kind": r.get("kind"),
                "status": r.get("status"),
                "username": r.get("actor_nome") or r.get("actor_cpf") or r.get("actor_email") or r.get("username"),
                "user_id": r.get("actor_cpf") or r.get("user_id"),
                "created_at": r.get("created_at"),
                "updated_at": r.get("updated_at"),
                "payload": r.get("payload") or {},
                "result": r.get("result"),
                "error": r.get("error"),
            })
        # Filtro de datas + paginação
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
    Busca uma submissão específica.
    """
    try:
        sub = db.get_submission(sid)
        if not sub:
            raise HTTPException(status_code=404, detail=f"submission {sid} não encontrada")
        # Normaliza retorno pontual
        return {
            "id": sub.get("id"),
            "kind": sub.get("kind"),
            "status": sub.get("status"),
            "username": sub.get("actor_nome") or sub.get("actor_cpf") or sub.get("actor_email") or sub.get("username"),
            "user_id": sub.get("actor_cpf") or sub.get("user_id"),
            "created_at": sub.get("created_at"),
            "updated_at": sub.get("updated_at"),
            "payload": sub.get("payload") or {},
            "result": sub.get("result"),
            "error": sub.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro ao buscar submission %s", sid)
        raise HTTPException(status_code=500, detail=f"erro ao buscar submission: {e}")


# --------------------------
# Endpoints não suportados (somente leitura)
# --------------------------
@router.post("/submit")
def submit_not_supported():
    raise HTTPException(
        status_code=409,
        detail="controle é somente leitura; use a automação de origem para submeter.",
    )


@router.post("/submissions/{sid}/download")
def download_not_supported(sid: str):
    raise HTTPException(
        status_code=409,
        detail=(
            "download deve ser feito na automação de origem "
            "(ex.: /api/automations/{kind}/submissions/{id}/download)."
        ),
    )
