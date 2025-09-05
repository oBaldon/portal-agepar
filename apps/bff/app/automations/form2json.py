# apps/bff/app/automations/form2json.py
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends
from starlette.responses import JSONResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field, EmailStr, ConfigDict, ValidationError
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from uuid import uuid4
from io import BytesIO
import json
import logging

from app.db import insert_submission, update_submission, get_submission, list_submissions, add_audit
from app.auth.rbac import require_roles_any  # RBAC

logger = logging.getLogger(__name__)

REQUIRED_ROLES = ("automations.form2json",)

# Protege TODO o router por padrão (JSON endpoints).
router = APIRouter(
    prefix="/api/automations/form2json",
    tags=["automations:form2json"],
)

# ==== helpers (idem)
def err_json(status: int, *, code: str, message: str, details: Any = None, hint: Optional[str] = None, received: Any = None):
    content: Dict[str, Any] = {"error": code, "message": message}
    if details is not None:
        content["details"] = details
    if hint is not None:
        content["hint"] = hint
    if received is not None:
        content["received"] = received
    return JSONResponse(status_code=status, content=content)

def pydantic_errors(exc: Exception):
    if isinstance(exc, ValidationError):
        out = []
        for e in exc.errors():
            loc = ".".join(str(p) for p in e.get("loc", []))
            out.append({"field": loc, "msg": e.get("msg"), "type": e.get("type")})
        return out
    return [{"field": "", "msg": str(exc)}]

def safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default

# ==== models (idem)
class FormItem(BaseModel):
    descricao: str = Field("", max_length=500)
    quantidade: int = Field(1, ge=0)

class Form2JsonIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    nome: Optional[str] = None
    email: Optional[EmailStr] = None
    departamento: Optional[str] = None
    prioridade: Literal["baixa", "media", "alta"] = "baixa"
    data: Optional[str] = None
    aceita_termos: bool = Field(False, alias="aceitaTermos")
    itens: List[FormItem] = Field(default_factory=list)

FORM2JSON_VERSION = "1.0.0"
KIND = "form2json"

SCHEMA = {
    "title": "Formulário para JSON",
    "version": FORM2JSON_VERSION,
    "fields": [
        {"name": "nome", "type": "text", "label": "Nome"},
        {"name": "email", "type": "email", "label": "Email"},
        {"name": "departamento", "type": "text", "label": "Departamento", "default": "AGEPAR"},
        {"name": "prioridade", "type": "select", "label": "Prioridade", "options": ["baixa","media","alta"], "default": "baixa"},
        {"name": "data", "type": "date", "label": "Data"},
        {"name": "aceitaTermos", "type": "checkbox", "label": "Aceito os termos"},
        {"name": "itens", "type": "array", "label": "Itens", "itemShape": {"descricao":"", "quantidade":1}},
    ]
}

def _build_payload(body: Form2JsonIn, actor: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "nome": (body.nome or None),
        "email": (body.email or None),
        "departamento": (body.departamento or None),
        "prioridade": body.prioridade,
        "data": (body.data or None),
        "aceitaTermos": bool(body.aceita_termos),
        "itens": [
            {"descricao": i.descricao.strip(), "quantidade": int(i.quantidade or 0)}
            for i in body.itens if (i.descricao or "").strip()
        ],
        "metadata": {
            "engine": f"{KIND}@{FORM2JSON_VERSION}",
            "geradoEm": datetime.utcnow().isoformat() + "Z",
            "actor": {"cpf": actor.get("cpf"), "nome": actor.get("nome"), "email": actor.get("email")},
        },
    }

# ==== Endpoints (agora com Depends) ==========================================

@router.get("/schema")
async def get_schema():
    try:
        return {"kind": KIND, "schema": SCHEMA}
    except Exception as e:
        logger.exception("schema error")
        return err_json(500, code="schema_error", message="Falha ao montar schema.", details=str(e))


@router.get("/submissions")
async def list_my_submissions(
    request: Request,
    user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES)),
    limit: int = 50,
    offset: int = 0,
):
    try:
        rows = list_submissions(kind=KIND, actor_cpf=user.get("cpf"), limit=limit, offset=offset)
        return {"items": rows, "limit": limit, "offset": offset}
    except Exception as e:
        logger.exception("list_submissions error")
        return err_json(500, code="storage_error", message="Falha ao listar suas submissões.", details=str(e))


@router.get("/submissions/{sid}")
async def get_submission_status(
    sid: str,
    user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES)),
):
    try:
        row = get_submission(sid)
    except Exception as e:
        logger.exception("get_submission storage error")
        return err_json(500, code="storage_error", message="Falha ao consultar submissão.", details=str(e))

    if not row:
        return err_json(404, code="not_found", message="Submissão não encontrada.", details={"sid": sid})

    if row.get("actor_cpf") != user.get("cpf"):
        return err_json(403, code="forbidden", message="Você não tem acesso a esta submissão.")

    return row


def _process_submission(sid: str, body: Form2JsonIn, actor: Dict[str, Any]):
    try:
        update_submission(sid, status="running")
    except Exception as e:
        logger.exception("update_submission to running failed")
        try:
            update_submission(sid, status="error", error=f"storage: {e}")
        except Exception:
            pass
        try:
            add_audit(KIND, "failed", actor, {"sid": sid, "error": f"storage: {e}"})
        except Exception:
            pass
        return

    try:
        payload = _build_payload(body, actor)
        result = payload
        update_submission(sid, status="done", result=json.dumps(result, ensure_ascii=False), error=None)
        add_audit(KIND, "completed", actor, {"sid": sid})
    except Exception as e:
        logger.exception("processing error")
        try:
            update_submission(sid, status="error", error=str(e))
        except Exception:
            pass
        try:
            add_audit(KIND, "failed", actor, {"sid": sid, "error": str(e)})
        except Exception:
            pass


@router.post("/submit")
async def submit(
    request: Request,
    background: BackgroundTasks,
    user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES)),
):
    # 1) Lê JSON cru
    try:
        raw = await request.json()
        if not isinstance(raw, dict):
            return err_json(
                400, code="invalid_json",
                message="O corpo da requisição deve ser um objeto JSON.",
                hint="Envie application/json com um objeto (chave/valor).",
            )
    except Exception as e:
        return err_json(
            400, code="invalid_json",
            message="Não foi possível interpretar o JSON enviado.",
            details=str(e),
            hint="Verifique o Content-Type e o formato JSON.",
        )

    # 2) Normalizações amigáveis
    def none_if_empty(v):
        return None if isinstance(v, str) and v.strip() == "" else v

    raw["nome"] = none_if_empty(raw.get("nome"))
    raw["email"] = none_if_empty(raw.get("email"))
    raw["departamento"] = none_if_empty(raw.get("departamento"))
    raw["data"] = none_if_empty(raw.get("data"))

    if "aceitaTermos" in raw and "aceita_termos" not in raw:
        raw["aceita_termos"] = bool(raw.get("aceitaTermos"))

    norm_itens = []
    itens = raw.get("itens") or []
    if not isinstance(itens, list):
        return err_json(
            400, code="invalid_field",
            message="O campo 'itens' deve ser uma lista.",
            received={"type": type(itens).__name__},
            hint="Envie 'itens' como array de objetos { descricao, quantidade }.",
        )

    for idx, it in enumerate(itens):
        if not isinstance(it, dict):
            return err_json(
                400, code="invalid_item",
                message=f"Item em 'itens[{idx}]' deve ser um objeto.",
                received={"value_type": type(it).__name__},
            )
        desc = (it.get("descricao") or "").strip()
        q = safe_int(it.get("quantidade", 0), default=0)
        norm_itens.append({"descricao": desc, "quantidade": q})
    raw["itens"] = norm_itens

    # 3) Validação
    try:
        body = Form2JsonIn.model_validate(raw)
    except Exception as e:
        return err_json(400, code="invalid_payload", message="O corpo enviado não passou na validação.", details=pydantic_errors(e), received=raw)

    # 4) Persistência
    sid = str(uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    try:
        insert_submission({
            "id": sid, "kind": KIND, "version": FORM2JSON_VERSION,
            "actor_cpf": user.get("cpf"), "actor_nome": user.get("nome"), "actor_email": user.get("email"),
            "payload": json.dumps(raw, ensure_ascii=False),
            "status": "queued", "result": None, "error": None,
            "created_at": now, "updated_at": now
        })
        add_audit(KIND, "submitted", user, {"sid": sid})
    except Exception as e:
        logger.exception("insert_submission error")
        return err_json(500, code="storage_error", message="Falha ao salvar a submissão.", details=str(e))

    # 5) Processamento assíncrono
    background.add_task(_process_submission, sid, body, user)
    return {"submissionId": sid, "status": "queued"}


@router.post("/submissions/{sid}/download")
async def download_result(
    sid: str,
    user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES)),
):
    try:
        row = get_submission(sid)
    except Exception as e:
        logger.exception("get_submission storage error (download)")
        return err_json(500, code="storage_error", message="Falha ao consultar submissão.", details=str(e))

    if not row:
        return err_json(404, code="not_found", message="Submissão não encontrada.", details={"sid": sid})

    if row.get("actor_cpf") != user.get("cpf"):
        return err_json(403, code="forbidden", message="Você não tem acesso a esta submissão.")

    status = row.get("status")
    if status != "done":
        return err_json(409, code="not_ready", message="Resultado ainda não está disponível para download.", details={"status": status}, hint="Aguarde o status 'done' e tente novamente.")

    data = row.get("result") or "{}"
    try:
        buf = BytesIO(data.encode("utf-8"))
    except Exception as e:
        logger.exception("encode error on download")
        return err_json(500, code="encoding_error", message="Falha ao preparar o arquivo para download.", details=str(e))

    base = "form"
    try:
        payload = json.loads(row.get("payload") or "{}")
        base = (payload.get("nome") or "form").strip().replace(" ", "_").lower() or "form"
    except Exception:
        pass

    filename = f"{base}_{datetime.utcnow().date().isoformat()}.json"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(buf, media_type="application/json; charset=utf-8", headers=headers)


# UI do iframe: queremos HTML amigável em 401/403,
# então NÃO usamos dependency aqui; chamamos manualmente o checker.
@router.get("/ui")
async def form2json_ui(request: Request):
    checker = require_roles_any(*REQUIRED_ROLES)
    try:
        checker(request)  # retorna user ou lança HTTPException
    except HTTPException as he:
        status = he.status_code
        msg = "Faça login para acessar esta automação." if status == 401 else "Você não tem permissão para acessar esta automação."
        html_err = f"""<!doctype html><meta charset="utf-8"/><title>Acesso</title>
        <div style="font-family:system-ui;padding:24px">
          <h1 style="margin:0 0 8px">{status}</h1>
          <p style="color:#334155">{msg}</p>
        </div>"""
        return HTMLResponse(html_err, status_code=status)

    # ... HTML normal (igual você já tinha) ...
    html = """<!doctype html>
    <!-- (mantém o mesmo HTML que você postou) -->
    """
    return HTMLResponse(html)
