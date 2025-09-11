# app/automations/dfd.py
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends
from starlette.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field, ConfigDict, ValidationError
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import uuid4
from io import BytesIO
import json
import logging
import os
import pathlib
import mimetypes
import re

from app.db import (
    insert_submission,
    update_submission,
    get_submission,
    list_submissions,
    add_audit,
    list_audits,
)
from app.auth.rbac import require_roles_any  # RBAC
from app.utils.docx_tools import (
    render_docx_template,
    convert_docx_to_pdf,
    get_docx_placeholders,
)

logger = logging.getLogger(__name__)

KIND = "dfd"
DFD_VERSION = "1.9.0"
REQUIRED_ROLES = ("automations.dfd",)

# Diretório com os modelos DOCX por diretoria
MODELS_DIR = os.environ.get("DFD_MODELS_DIR", "/app/templates/dfd_models")

# Diretório com os HTMLs desta automação
TPL_DIR = pathlib.Path(__file__).resolve().parent / "templates" / "dfd"


# ---------------------- Helpers ----------------------
def err_json(status: int, **payload):
    return StreamingResponse(
        BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
        status_code=status,
        media_type="application/json; charset=utf-8",
    )


def _to_obj(x, default=None):
    """Aceita dict/list/str/bytes; retorna dict/list. Evita quebrar entre SQLite e Postgres."""
    if x is None:
        return {} if default is None else default
    if isinstance(x, (dict, list)):
        return x
    if isinstance(x, (bytes, bytearray)):
        try:
            return json.loads(x.decode("utf-8"))
        except Exception:
            return {} if default is None else default
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return {} if default is None else default
    return {} if default is None else default


def none_if_empty(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return v


def _safe_comp(txt: str) -> str:
    """Sanitiza componente de filename (sem espaços e sem separadores perigosos)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(txt)).strip("_")


def _list_models() -> List[Dict[str, Any]]:
    """Lista pastas válidas (com model.docx) em MODELS_DIR."""
    items: List[Dict[str, Any]] = []
    base = pathlib.Path(MODELS_DIR)
    if not base.exists() or not base.is_dir():
        return items
    for child in sorted(base.iterdir()):
        if child.is_dir() and (child / "model.docx").exists():
            items.append({"slug": child.name, "file": "model.docx"})
    return items


def _get_model_path(slug: str) -> Optional[str]:
    """Retorna caminho absoluto de <slug>/model.docx, se existir."""
    d = pathlib.Path(MODELS_DIR) / slug
    docx = d / "model.docx"
    if docx.exists():
        return str(docx)
    return None


def _owns_submission(row: Dict[str, Any], user: Dict[str, Any]) -> bool:
    """Permite acesso se CPF bater, ou se não houver CPF gravado mas o e-mail bater."""
    u_cpf = (user.get("cpf") or "").strip() or None
    u_email = (user.get("email") or "").strip() or None
    owner_cpf = (row.get("actor_cpf") or "").strip() or None
    owner_email = (row.get("actor_email") or "").strip() or None
    return bool(
        (owner_cpf and u_cpf and owner_cpf == u_cpf) or
        (not owner_cpf and owner_email and u_email and owner_email == u_email)
    )

def _read_html(name: str) -> str:
    """Carrega um arquivo HTML de TPL_DIR."""
    path = TPL_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------- Models ----------------------
MAX_ASSUNTO_LEN = 200  # agora representa o OBJETO digitado


class DfdIn(BaseModel):
    """Campos mínimos para o MVP do DFD."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    modelo_slug: str = Field(..., alias="modeloSlug")  # diretoria (nome da pasta)
    numero: str  # nº do memorando

    # O usuário digita apenas o OBJETO; o assunto final é montado pelo sistema.
    assunto: str = Field(..., min_length=1, max_length=MAX_ASSUNTO_LEN)

    # Ano de execução do PCA (4 dígitos)
    pca_ano: str = Field(..., alias="pcaAno", pattern=r"^\d{4}$")

    # Três campos de texto livres (exemplos)
    exemplo1: str = Field("", max_length=4000)
    exemplo2: str = Field("", max_length=4000)
    exemplo3: str = Field("", max_length=4000)


SCHEMA = {
    "title": "DFD — Documento de Formalização da Demanda (MVP)",
    "version": DFD_VERSION,
    "fields": [
        {"name": "modeloSlug", "type": "select", "label": "Diretoria"},
        {"name": "numero", "type": "text", "label": "Nº do Memorando"},
        {"name": "assunto", "type": "text", "label": "Objeto"},
        {"name": "pcaAno", "type": "text", "label": "Ano de execução do PCA"},
        {"name": "exemplo1", "type": "textarea", "label": "Exemplo 1"},
        {"name": "exemplo2", "type": "textarea", "label": "Exemplo 2"},
        {"name": "exemplo3", "type": "textarea", "label": "Exemplo 3"},
    ],
}

# Mapeamento amigável de campos → rótulos/limites (para mensagens de validação)
FIELD_INFO: Dict[str, Dict[str, Any]] = {
    "modeloSlug": {"label": "Diretoria"},
    "modelo_slug": {"label": "Diretoria"},  # nome interno pydantic
    "numero": {"label": "Nº do Memorando"},
    "assunto": {"label": "Objeto", "max_length": MAX_ASSUNTO_LEN, "min_length": 1},
    "pcaAno": {"label": "Ano de execução do PCA", "pattern": r"^\d{4}$"},
    "pca_ano": {"label": "Ano de execução do PCA", "pattern": r"^\d{4}$"},
    "exemplo1": {"label": "Exemplo 1", "max_length": 4000},
    "exemplo2": {"label": "Exemplo 2", "max_length": 4000},
    "exemplo3": {"label": "Exemplo 3", "max_length": 4000},
}


def _format_validation_errors(ve: ValidationError) -> List[str]:
    """Gera mensagens legíveis por campo a partir dos erros do Pydantic v2."""
    msgs: List[str] = []
    for err in ve.errors():
        loc = err.get("loc") or ()
        field_key = str(loc[-1]) if loc else "campo"
        info = FIELD_INFO.get(field_key) or FIELD_INFO.get(
            field_key.replace("modelo_slug", "modeloSlug"), {}
        )
        label = info.get("label", field_key)
        typ = err.get("type", "")
        ctx = err.get("ctx") or {}
        msg = err.get("msg", "")

        if typ == "string_too_long" and "max_length" in ctx:
            limit = ctx["max_length"]
            msgs.append(f"Campo '{label}' excedeu o limite de {limit} caracteres.")
        elif typ == "string_too_short" and "min_length" in ctx:
            minimum = ctx["min_length"]
            msgs.append(f"Campo '{label}' deve ter pelo menos {minimum} caractere(s).")
        elif typ == "string_pattern_mismatch" and "pattern" in ctx:
            if field_key in ("pcaAno", "pca_ano"):
                msgs.append(f"Campo '{label}' deve conter 4 dígitos (ex.: 2025).")
            else:
                msgs.append(f"Campo '{label}' não está no formato esperado.")
        elif typ == "string_type":
            msgs.append(f"Campo '{label}' deve ser texto.")
        elif typ == "missing":
            msgs.append(f"Campo '{label}' é obrigatório.")
        else:
            msgs.append(f"Campo '{label}': {msg}")
    return msgs


router = APIRouter(prefix=f"/api/automations/{KIND}", tags=[f"automation:{KIND}"])


@router.get("/schema")
async def get_schema():
    return {"kind": KIND, "schema": SCHEMA}


@router.get("/models")
async def get_models(user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES))):
    try:
        return {"items": _list_models()}
    except Exception as e:
        logger.exception("list models failed")
        return err_json(500, code="storage_error", message="Falha ao listar modelos.", details=str(e))


@router.get("/submissions")
async def list_my_submissions(
    request: Request,
    user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES)),
    limit: int = 50,
    offset: int = 0,
):
    # 1) Identidade do usuário: prioriza CPF; se não houver, usa e-mail.
    cpf = (user.get("cpf") or "").strip() or None
    email = (user.get("email") or "").strip() or None

    # 2) Se não houver CPF nem e-mail, não prossegue (evita listar tudo por engano).
    if not cpf and not email:
        return err_json(
            422,
            code="identity_missing",
            message="Não foi possível identificar o usuário para filtrar as submissões (sem CPF e e-mail). Faça login novamente."
        )

    try:
        # 3) Busca filtrando por CPF; se não houver CPF, cai para e-mail.
        rows = list_submissions(
            kind=KIND,
            actor_cpf=cpf,
            actor_email=None if cpf else email,
            limit=limit,
            offset=offset,
        )
        return {"items": rows, "limit": limit, "offset": offset}
    except Exception as e:
        logger.exception("list_submissions storage error")
        return err_json(500, code="storage_error", message="Falha ao consultar submissões.", details=str(e))


@router.get("/submissions/{sid}")
async def get_my_submission(
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

    if not _owns_submission(row, user):
        return err_json(403, code="forbidden", message="Você não tem acesso a esta submissão.")

    return row


def _process_submission(sid: str, body: DfdIn, actor: Dict[str, Any]) -> None:
    """Processa a submissão: preenche o DOCX, tenta converter para PDF, salva e audita."""
    try:
        update_submission(sid, status="running")
        add_audit(KIND, "running", actor, {"sid": sid})
    except Exception as e:
        logger.exception("update to running failed")
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
        raw = body.model_dump(by_alias=True)

        tpl_path = _get_model_path(raw["modeloSlug"])
        if not tpl_path:
            raise RuntimeError(
                f"Modelo '{raw['modeloSlug']}' não encontrado. "
                f"Converta o arquivo para 'model.docx' em /templates/dfd_models/{raw['modeloSlug']}/."
            )
        logger.info("[DFD] Processando submissão %s | modelo=%s | tpl_path=%s", sid, raw["modeloSlug"], tpl_path)

        out_dir = "/app/data/files/dfd"
        os.makedirs(out_dir, exist_ok=True)
        numero_safe = _safe_comp(raw["numero"])
        base = f"dfd_{raw['modeloSlug'].lower()}_{numero_safe}"
        today_iso = datetime.utcnow().date().isoformat()

        # Monta ASSUNTO final: "DFD - PCA <ano> - <objeto>"
        objeto = (raw.get("assunto") or "").strip()
        pca_ano = (raw.get("pcaAno") or "").strip()
        assunto_final = f"DFD - PCA {pca_ano} - {objeto}"

        ctx = {
            "diretoria": raw["modeloSlug"],
            "numero": raw["numero"],
            "assunto": assunto_final,  # usado no cabeçalho/timbre
            "pca_ano": pca_ano,        # usado no texto introdutório do corpo
            "data": today_iso,
            "exemplo1": raw.get("exemplo1") or "",
            "exemplo2": raw.get("exemplo2") or "",
            "exemplo3": raw.get("exemplo3") or "",
        }

        # Log de placeholders (apenas informativo)
        placeholders = get_docx_placeholders(tpl_path)
        logger.info("[DFD] Placeholders detectados (%d): %s", len(placeholders), placeholders)
        logger.info("[DFD] Assunto final: %s", assunto_final)

        # Gera DOCX
        docx_out = f"{out_dir}/{sid}.docx"
        render_docx_template(tpl_path, ctx, docx_out)
        try:
            size_docx = os.path.getsize(docx_out)
        except Exception:
            size_docx = -1
        logger.info("[DFD] DOCX gerado | path=%s | size=%d", docx_out, size_docx)

        # Tenta PDF
        pdf_out = f"{out_dir}/{sid}.pdf"
        filename_docx = f"{base}_{today_iso}.docx"
        filename_pdf = f"{base}_{today_iso}.pdf"

        pdf_ok = convert_docx_to_pdf(docx_out, pdf_out)

        # Compat primário (mantém rota antiga funcionando)
        file_path = pdf_out if pdf_ok else docx_out
        filename = filename_pdf if pdf_ok else filename_docx

        result = {
            # primários (retrocompat)
            "file_path": file_path,
            "filename": filename,
            # novos campos explícitos
            "file_path_docx": docx_out,
            "filename_docx": filename_docx,
            "file_path_pdf": pdf_out if pdf_ok else None,
            "filename_pdf": filename_pdf if pdf_ok else None,
            # meta
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "engine": f"{KIND}@{DFD_VERSION}",
            # opcionalmente, persistimos o assunto final para a tela de histórico
            "assunto": assunto_final,
        }
        update_submission(sid, status="done", result=result, error=None)
        add_audit(KIND, "completed", actor, {"sid": sid, "filename": filename})

        try:
            size_final = os.path.getsize(file_path)
        except Exception:
            size_final = -1
        logger.info("[DFD] Submissão %s finalizada | entregue=%s (%d bytes)", sid, filename, size_final)

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
async def submit_dfd(
    request: Request,
    body: Dict[str, Any],
    background: BackgroundTasks,
    user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES)),
):
    raw = {
        "modeloSlug": none_if_empty(body.get("modeloSlug")),
        "numero": (body.get("numero") or "").strip(),
        # usuário digita apenas o OBJETO
        "assunto": (body.get("assunto") or "").strip(),
        "pcaAno": (body.get("pcaAno") or "").strip(),
        "exemplo1": (body.get("exemplo1") or "").strip(),
        "exemplo2": (body.get("exemplo2") or "").strip(),
        "exemplo3": (body.get("exemplo3") or "").strip(),
    }
    if not raw["modeloSlug"]:
        return err_json(422, code="validation_error", message="Diretoria é obrigatória.")
    if not raw["numero"]:
        return err_json(422, code="validation_error", message="Número do memorando é obrigatório.")

    try:
        payload = DfdIn(**raw)
    except ValidationError as ve:
        # Mensagens detalhadas por campo
        friendly = _format_validation_errors(ve)
        logger.info("[DFD] validation_error: %s", friendly)
        return err_json(422, code="validation_error", message="Erro de validação nos campos.", details={"errors": friendly})
    except Exception as ve:
        logger.exception("validation error on submit")
        return err_json(422, code="validation_error", message="Erro de validação.", details=str(ve))

    sid = str(uuid4())
    sub = {
        "id": sid,
        "kind": KIND,
        "version": DFD_VERSION,
        "actor_cpf": user.get("cpf"),
        "actor_nome": user.get("nome"),
        "actor_email": user.get("email"),
        # passa dict; o db.py (Postgres) persiste como JSONB
        "payload": payload.model_dump(by_alias=True, exclude_none=True),
        "status": "queued",
        "result": None,
        "error": None,
    }
    try:
        insert_submission(sub)
        add_audit(KIND, "submitted", user, {"sid": sid})
    except Exception as e:
        logger.exception("insert_submission failed")
        return err_json(500, code="storage_error", message="Falha ao salvar a submissão.", details=str(e))

    logger.info(
        "[DFD] Submissão %s criada por %s (%s) | modelo=%s | numero=%s",
        sid, user.get("nome"), user.get("cpf"), raw["modeloSlug"], raw["numero"]
    )

    background.add_task(_process_submission, sid, payload, user)
    return {"submissionId": sid, "status": "queued"}


@router.post("/submissions/{sid}/download")
async def download_result(
    sid: str,
    user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES)),
):
    """Rota antiga: baixa o arquivo “primário” (PDF se existir, senão DOCX)."""
    try:
        row = get_submission(sid)
    except Exception as e:
        logger.exception("get_submission (download) failed")
        return err_json(500, code="storage_error", message="Falha ao consultar submissão.", details=str(e))

    if not row:
        return err_json(404, code="not_found", message="Submissão não encontrada.", details={"sid": sid})

    if not _owns_submission(row, user):
        return err_json(403, code="forbidden", message="Você não tem acesso a esta submissão.")

    if row.get("status") != "done":
        return err_json(409, code="not_ready", message="Resultado ainda não está pronto.", details={"status": row.get("status")})

    try:
        result = _to_obj(row.get("result"), {})
        file_path = result.get("file_path")
        filename = result.get("filename") or f"dfd_{sid}.pdf"
        if not file_path or not os.path.exists(file_path):
            return err_json(410, code="file_not_found", message="Arquivo não está mais disponível.", details={"sid": sid})

        with open(file_path, "rb") as f:
            data = f.read()

        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return StreamingResponse(
            BytesIO(data),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.exception("download error")
        return err_json(500, code="download_error", message="Falha ao preparar o download.", details=str(e))


@router.post("/submissions/{sid}/download/{fmt}")
async def download_result_fmt(
    sid: str,
    fmt: str,
    user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES)),
):
    """Novo: baixa especificamente PDF ou DOCX."""
    if fmt not in ("pdf", "docx"):
        return err_json(400, code="bad_request", message="Formato inválido. Use 'pdf' ou 'docx'.")

    try:
        row = get_submission(sid)
    except Exception as e:
        logger.exception("get_submission (download fmt) failed")
        return err_json(500, code="storage_error", message="Falha ao consultar submissão.", details=str(e))

    if not row:
        return err_json(404, code="not_found", message="Submissão não encontrada.", details={"sid": sid})

    if not _owns_submission(row, user):
        return err_json(403, code="forbidden", message="Você não tem acesso a esta submissão.")

    if row.get("status") != "done":
        return err_json(409, code="not_ready", message="Resultado ainda não está pronto.", details={"status": row.get("status")})

    try:
        result = _to_obj(row.get("result"), {})
        if fmt == "pdf":
            file_path = result.get("file_path_pdf") or None
            filename = result.get("filename_pdf") or None
            if not file_path or not filename:
                return err_json(409, code="not_available", message="PDF não disponível para esta submissão.")
        else:
            file_path = result.get("file_path_docx") or result.get("file_path")  # fallback
            filename = result.get("filename_docx") or (result.get("filename") or f"dfd_{sid}.docx")

        if not file_path or not os.path.exists(file_path):
            return err_json(410, code="file_not_found", message="Arquivo não está mais disponível.", details={"sid": sid, "fmt": fmt})

        with open(file_path, "rb") as f:
            data = f.read()

        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return StreamingResponse(
            BytesIO(data),
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.exception("download fmt error")
        return err_json(500, code="download_error", message="Falha ao preparar o download.", details=str(e))


@router.get("/audits")
async def list_audits_admin(
    user: Dict[str, Any] = Depends(require_roles_any("admin")),
    limit: int = 50,
    offset: int = 0,
):
    try:
        rows = list_audits(kind=KIND, limit=limit, offset=offset)
        return {"items": rows, "limit": limit, "offset": offset}
    except Exception as e:
        logger.exception("list_audits storage error")
        return err_json(500, code="storage_error", message="Falha ao consultar auditoria.", details=str(e))


@router.get("/ui")
@router.get("/ui/")  # aceita com ou sem barra final
async def dfd_ui(request: Request):
    # Checagem manual para retornar HTML amigável em 401/403
    checker = require_roles_any(*REQUIRED_ROLES)
    try:
        checker(request)
    except HTTPException as he:
        status = he.status_code
        msg = "Faça login para acessar esta automação." if status == 401 else "Você não tem permissão para acessar esta automação."
        html_err = f"""<!doctype html><meta charset="utf-8"/><title>Acesso</title>
        <div style="font-family:system-ui;padding:24px">
          <h1 style="margin:0 0 8px">{status}</h1>
          <p style="color:#334155">{msg}</p>
        </div>"""
        return HTMLResponse(html_err, status_code=status)

    # HTML simples, sem f-string (para não conflitar com {{ }} do JS/CSS)
    html = _read_html("ui.html")
    return HTMLResponse(html)


@router.get("/ui/history")
@router.get("/ui/history/")
async def dfd_history_ui(request: Request):
    # Reaproveita o guard de RBAC para esta página também
    checker = require_roles_any(*REQUIRED_ROLES)
    try:
        checker(request)
    except HTTPException as he:
        status = he.status_code
        msg = "Faça login para acessar esta automação." if status == 401 else "Você não tem permissão para acessar esta automação."
        html_err = f"""<!doctype html><meta charset="utf-8"/><title>Acesso</title>
        <div style="font-family:system-ui;padding:24px">
          <h1 style="margin:0 0 8px">{status}</h1>
          <p style="color:#334155">{msg}</p>
        </div>"""
        return HTMLResponse(html_err, status_code=status)

    html = _read_html("history.html")
    return HTMLResponse(html)
