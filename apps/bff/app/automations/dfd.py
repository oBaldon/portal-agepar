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
    html = """<!doctype html>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>DFD — Documento de Formalização da Demanda (MVP)</title>
<style>
  :root { --fg:#0f172a; --muted:#475569; --bg:#f8fafc; --card:#ffffff; --pri:#2563eb; }
  * { box-sizing: border-box; }
  html, body { margin:0; padding:0; }
  body { font-family: system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial,'Noto Sans','Apple Color Emoji','Noto Color Emoji',sans-serif; background:var(--bg); color:var(--fg); }
  .wrap { max-width: 960px; margin: 24px auto; padding: 0 16px; }
  h1 { font-size: 20px; margin: 0 0 12px; }
  .header { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px; }
  .card { background:var(--card); border:1px solid #e2e8f0; border-radius: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.04); padding: 16px; }
  label { display:block; font-size: 12px; color: var(--muted); margin: 12px 0 6px; }
  input, textarea, select { width: 100%; padding: 10px 12px; border:1px solid #cbd5e1; border-radius: 10px; font: inherit; background:#fff; }
  textarea { min-height: 100px; resize: vertical; }
  .row { display:flex; gap: 12px; }
  .col { flex:1; min-width: 0; }
  .actions { display:flex; gap: 12px; align-items:center; }
  .btn { background: var(--pri); color:#fff; border:1px solid transparent; border-radius: 10px; padding: 10px 16px; cursor:pointer; transition:.16s ease; }
  .btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(2,6,23,.08); }
  .btn:focus-visible { outline: 2px solid #93c5fd; outline-offset: 2px; }
  .btn.secondary { background:#fff; color:#334155; border-color:#cbd5e1; }
  .btn.secondary:hover { background:#f8fafc; }
  .btn.small { padding: 8px 12px; font-size: 12px; }
  .btn[disabled] { opacity:.6; cursor: not-allowed; transform:none; box-shadow:none; }
  .btn-row { display:flex; gap:10px; flex-wrap:wrap; }
  .note { font-size:12px; color:var(--muted); }
  .status { margin-top:12px; font-size:13px; }
  .list { margin-top: 24px; }
  .item { padding:12px; border:1px dashed #e2e8f0; border-radius: 10px; margin-bottom: 8px; background:#fff; }
  .item .meta { margin-bottom:8px; }
  .badge { display:inline-block; font-size:11px; padding:2px 6px; border-radius: 999px; background:#eef2ff; color:#1e3a8a; margin-right:6px; }

  /* help / tooltip */
  .inline-help { display:inline-flex; align-items:center; position:relative; margin-left:6px; }
  .inline-help .help {
    width:18px; height:18px; border-radius:999px; background:#e2e8f0; color:#0f172a;
    border:1px solid #cbd5e1; font-size:12px; line-height:16px; text-align:center;
    padding:0; cursor:pointer;
  }
  .inline-help .help:hover { background:#dbeafe; border-color:#93c5fd; }
  .inline-help .help:focus-visible { outline:2px solid #93c5fd; outline-offset:2px; }
  .inline-help .tip {
    position:absolute; top:120%; left:0; z-index:10; min-width: 220px; max-width: 360px;
    background:#0f172a; color:#fff; padding:8px 10px; border-radius:10px; font-size:12px;
    box-shadow: 0 8px 24px rgba(2,6,23,.18); pointer-events:none;
    opacity:0; transform: translateY(-4px); transition: opacity .12s ease, transform .12s ease;
  }
  .inline-help:hover .tip, .inline-help:focus-within .tip { opacity:1; transform: translateY(0); }
  .tip code { background: rgba(255,255,255,.12); padding:0 4px; border-radius:4px; }
</style>

<div class="wrap">
  <div class="header">
    <h1>DFD — Documento de Formalização da Demanda (MVP)</h1>
    <a class="btn secondary small" href="/api/automations/dfd/ui/history" rel="noopener">Meus DFDs</a>
  </div>

  <div class="card">
    <form id="f">
      <div class="row">
        <div class="col">
          <label>
            Diretoria
            <span class="inline-help">
              <button type="button" class="help" aria-label="Ajuda sobre Diretoria">!</button>
              <span class="tip">Selecione o timbre/cabeçalho correspondente. As opções vêm de <code>/templates/dfd_models</code>.</span>
            </span>
          </label>
          <select name="modeloSlug" id="modeloSlug" required>
            <option value="">-- Selecionar --</option>
          </select>
          <div class="note">Carrega pastas de /templates/dfd_models.</div>
        </div>

        <div class="col">
          <label>
            Nº do memorando
            <span class="inline-help">
              <button type="button" class="help" aria-label="Ajuda sobre Nº do memorando">!</button>
              <span class="tip">Use o padrão da sua unidade (ex.: <code>012/2025</code>). Esse número aparece no cabeçalho.</span>
            </span>
          </label>
          <input name="numero" placeholder="Ex.: 0XX/202X" required />
        </div>
      </div>

      <label>
        Objeto
        <span class="inline-help">
          <button type="button" class="help" aria-label="Ajuda sobre Objeto">!</button>
          <span class="tip">Digite apenas o objeto (ex.: <em>Aquisição de software X</em>). O assunto final será montado como <code>DFD - PCA [ano] - [objeto]</code>.</span>
        </span>
      </label>
      <input name="assunto" placeholder="Ex.: Aquisição de software X" required />
      <div class="note">O assunto final será montado automaticamente como <code>DFD - PCA [ano] - [objeto]</code>.</div>

      <label>
        Ano de execução do PCA
        <span class="inline-help">
          <button type="button" class="help" aria-label="Ajuda sobre Ano de execução do PCA">!</button>
          <span class="tip">Informe 4 dígitos (ex.: <code>2025</code>). É usado no cabeçalho e no texto introdutório.</span>
        </span>
      </label>
      <input name="pcaAno" placeholder="Ex.: 2025" pattern="\\d{4}" required />

      <label>
        Exemplo 1
        <span class="inline-help">
          <button type="button" class="help" aria-label="Ajuda sobre Exemplo 1">!</button>
          <span class="tip">Campo livre. Cada quebra de linha será respeitada no documento final.</span>
        </span>
      </label>
      <textarea name="exemplo1"></textarea>

      <label>
        Exemplo 2
        <span class="inline-help">
          <button type="button" class="help" aria-label="Ajuda sobre Exemplo 2">!</button>
          <span class="tip">Campo livre. Utilize para detalhar justificativas, escopo, etc.</span>
        </span>
      </label>
      <textarea name="exemplo2"></textarea>

      <label>
        Exemplo 3
        <span class="inline-help">
          <button type="button" class="help" aria-label="Ajuda sobre Exemplo 3">!</button>
          <span class="tip">Campo livre. Pode ser usado para referências, prazos, anexos relacionados.</span>
        </span>
      </label>
      <textarea name="exemplo3"></textarea>

      <div class="actions" style="margin-top:16px">
        <button class="btn" id="submitBtn">Gerar DFD</button>
        <span class="status" id="status"></span>
      </div>
    </form>
  </div>

  <div class="list" id="subs"></div>
</div>

<script>
  const f = document.getElementById('f');
  const statusEl = document.getElementById('status');
  const subsEl = document.getElementById('subs');
  const submitBtn = document.getElementById('submitBtn');
  const modeloSel = document.getElementById('modeloSlug');

  async function loadModels(){
    try {
      const r = await fetch('./models');
      if (!r.ok) return;
      const data = await r.json();
      const items = (data && data.items) || [];
      items.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.slug;
        opt.textContent = m.slug;
        modeloSel.appendChild(opt);
      });
    } catch(e) {}
  }

  function formToPayload(form) {
    const data = new FormData(form);
    const obj = Object.fromEntries(data.entries());
    return obj;
  }

  async function submit(evt) {
    evt.preventDefault();
    submitBtn.disabled = true;
    statusEl.textContent = 'Enviando...';

    const payload = formToPayload(f);

    const res = await fetch('./submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) {
      let msg = (data && data.message) ? data.message : String(res.status);
      const details = (data && data.details && data.details.errors);
      if (Array.isArray(details) && details.length) {
        msg += ' — ' + details.join(' | ');
      }
      statusEl.textContent = 'Erro: ' + msg;
      submitBtn.disabled = false;
      return;
    }

    statusEl.textContent = 'Fila criada, aguardando processamento...';
    const sid = data.submissionId;
    let tries = 0;
    let row = null;
    while (tries < 120) {
      await new Promise(r => setTimeout(r, 1000));
      const r = await fetch('./submissions/' + sid);
      row = await r.json();
      if (row.status === 'done' || row.status === 'error') break;
      tries++;
    }
    if (!row) {
      statusEl.textContent = 'Falha ao acompanhar processamento.';
      submitBtn.disabled = false;
      return;
    }

    if (row.status === 'done') {
      statusEl.textContent = 'Pronto! Download do arquivo abaixo.';
      const div = document.createElement('div');
      div.className = 'item';

      const toObj = (x) => {
        if (!x) return {};
        if (typeof x === 'string') { try { return JSON.parse(x); } catch { return {}; } }
        if (typeof x === 'object') return x;
        return {};
      };

      const d = toObj(row.result);

      // exibe nome sem extensão
      const displayName = (() => {
        const n = (d.filename || d.filename_pdf || d.filename_docx || '').trim();
        const i = n.lastIndexOf('.');
        return i > 0 ? n.slice(0, i) : n;
      })();

      const meta = document.createElement('div');
      meta.className = 'meta';

      const badge = document.createElement('span');
      badge.className = 'badge';
      badge.textContent = 'done';

      const when = new Date(d.generated_at || Date.now()).toLocaleString();
      const title = document.createElement('span');
      title.textContent = ` ${displayName} — ${when}`;

      meta.appendChild(badge);
      meta.appendChild(title);

      const buttons = document.createElement('div');
      buttons.className = 'btn-row';

      // Botão PDF (se existir)
      if (d.filename_pdf && d.file_path_pdf) {
        const btnPdf = document.createElement('button');
        btnPdf.className = 'btn';
        btnPdf.textContent = 'Baixar PDF';
        btnPdf.onclick = async () => {
          try {
            const dl = await fetch('./submissions/' + sid + '/download/pdf', { method: 'POST' });
            if (!dl.ok) throw new Error('Falha no download (PDF)');
            const blob = await dl.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = (d.filename_pdf || ('dfd_' + sid + '.pdf'));
            a.click();
            URL.revokeObjectURL(a.href);
          } catch (e) {
            alert('Não foi possível baixar o PDF.');
          }
        };
        buttons.appendChild(btnPdf);
      }

      // Botão DOCX (sempre deve existir)
      const btnDocx = document.createElement('button');
      btnDocx.className = 'btn secondary';
      btnDocx.textContent = 'Baixar DOCX';
      btnDocx.onclick = async () => {
        try {
          const dl = await fetch('./submissions/' + sid + '/download/docx', { method: 'POST' });
          if (!dl.ok) throw new Error('Falha no download (DOCX)');
          const blob = await dl.blob();
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = (d.filename_docx || ('dfd_' + sid + '.docx'));
          a.click();
          URL.revokeObjectURL(a.href);
        } catch (e) {
          alert('Não foi possível baixar o DOCX.');
        }
      };
      buttons.appendChild(btnDocx);

      div.appendChild(meta);
      div.appendChild(buttons);
      subsEl.prepend(div);
    } else {
      statusEl.textContent = 'Erro ao gerar: ' + (row.error || 'desconhecido');
    }
    submitBtn.disabled = false;
  }

  loadModels();
  f.addEventListener('submit', submit);
</script>
"""
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

    html = """<!doctype html>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Histórico — Meus DFDs</title>
<style>
  :root { --fg:#0f172a; --muted:#475569; --bg:#f8fafc; --card:#ffffff; --pri:#2563eb; }
  * { box-sizing: border-box; }
  body { margin:0; font-family: system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,'Helvetica Neue',Arial,'Noto Sans','Apple Color Emoji','Noto Color Emoji',sans-serif; background:var(--bg); color:var(--fg); }
  .wrap { max-width: 1100px; margin: 24px auto; padding: 0 16px; }
  h1 { font-size: 20px; margin: 0; }
  .card { background:var(--card); border:1px solid #e2e8f0; border-radius: 14px; box-shadow: 0 1px 2px rgba(0,0,0,.04); padding: 16px; }
  .toolbar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin: 12px 0 14px; }
  .toolbar input, .toolbar select { padding: 10px 12px; border:1px solid #cbd5e1; border-radius: 10px; font: inherit; background:#fff; }
  .btn { background: var(--pri); color:#fff; border:1px solid transparent; border-radius: 10px; padding: 10px 16px; cursor:pointer; transition:.16s ease; }
  .btn.secondary { background:#fff; color:#334155; border-color:#cbd5e1; }
  .btn.ghost { background:transparent; color:#334155; border:1px solid #cbd5e1; }
  .btn.small { padding:8px 12px; font-size:12px; }
  .btn[disabled] { opacity:.6; cursor:not-allowed; }
  table { width:100%; border-collapse: collapse; }
  th, td { text-align:left; padding:10px 12px; border-bottom:1px solid #e2e8f0; vertical-align: top; }
  th { font-size:12px; color:#475569; text-transform: uppercase; letter-spacing:.02em; }
  .badge { display:inline-block; font-size:11px; padding:2px 6px; border-radius: 999px; background:#eef2ff; color:#1e3a8a; }
  .badge.err { background:#fee2e2; color:#991b1b; }
  .badge.warn{ background:#fef3c7; color:#92400e; }
  .btn-row { display:flex; gap:8px; flex-wrap:wrap; }
  .muted { color:#64748b; }
</style>

<div class="wrap">
  <div style="display:flex; align-items:center; justify-content:space-between; gap:12px;">
    <h1>Histórico — Meus DFDs</h1>
    <a href="../ui" class="btn secondary small">← Voltar ao formulário</a>
  </div>

  <div class="card" style="margin-top:12px;">
    <div class="toolbar">
      <input id="q" placeholder="Buscar por nº do memorando, objeto, assunto…" style="flex:1; min-width:220px;" />
      <select id="sort">
        <option value="date_desc">Mais recentes</option>
        <option value="date_asc">Mais antigos</option>
        <option value="numero_asc">Número (A→Z)</option>
        <option value="numero_desc">Número (Z→A)</option>
      </select>
      <button id="refresh" class="btn ghost">Recarregar</button>
      <button id="more" class="btn secondary">Carregar mais</button>
    </div>

    <div style="overflow:auto;">
      <table id="tbl">
        <thead>
          <tr>
            <th style="width:160px">Data</th>
            <th style="width:160px">Nº Memorando</th>
            <th>Assunto</th>
            <th style="width:120px">Status</th>
            <th style="width:220px">Ações</th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>

    <div id="empty" class="muted" style="display:none; padding:8px 0;">Nenhuma submissão encontrada.</div>
  </div>
</div>

<script>
  const tbody = document.getElementById('tbody');
  const emptyEl = document.getElementById('empty');
  const q = document.getElementById('q');
  const sortSel = document.getElementById('sort');
  const btnMore = document.getElementById('more');
  const btnRefresh = document.getElementById('refresh');

  let items = [];     // acumulado do servidor
  let filtered = [];  // filtrado + ordenado
  let offset = 0;
  const limit = 20;
  let loading = false;
  let end = false;    // recebeu menos que limit

  function parseJSON(x, fallback = {}) {
    if (!x) return fallback;
    if (typeof x === 'string') {
      try { return JSON.parse(x); } catch { return fallback; }
    }
    if (typeof x === 'object') return x; // já é JSON (Postgres)
    return fallback;
  }
  function buildAssuntoFrom(row) {
    // tenta result.assunto; cai para payload: objeto + pcaAno; senão vazio
    const result = parseJSON(row.result || "{}", {});
    if (result && result.assunto) return result.assunto;
    const payload = parseJSON(row.payload || "{}", {});
    const obj = payload.assunto || "";
       const ano = payload.pcaAno || payload.pca_ano || "";
    return (obj && ano) ? (`DFD - PCA ${ano} - ${obj}`) : (obj || "");
  }
  function rowDate(row) {
    const result = parseJSON(row.result || "{}", {});
    const when = result.generated_at || row.updated_at || row.created_at;
    return when ? new Date(when) : new Date();
  }
  function rowNumero(row) {
    const payload = parseJSON(row.payload || "{}", {});
    return payload.numero || "";
  }

  function renderTable() {
    tbody.innerHTML = "";
    if (filtered.length === 0) {
      emptyEl.style.display = "";
      return;
    }
    emptyEl.style.display = "none";

    for (const row of filtered) {
      const tr = document.createElement("tr");

      // Data
      const tdDate = document.createElement("td");
      tdDate.textContent = rowDate(row).toLocaleString();
      tr.appendChild(tdDate);

      // Número
      const tdNum = document.createElement("td");
      tdNum.textContent = rowNumero(row);
      tr.appendChild(tdNum);

      // Assunto
      const tdAss = document.createElement("td");
      tdAss.textContent = buildAssuntoFrom(row);
      tr.appendChild(tdAss);

      // Status
      const tdSt = document.createElement("td");
      const st = row.status || "queued";
      const badge = document.createElement("span");
      badge.className = "badge" + (st === "error" ? " err" : (st !== "done" ? " warn" : ""));
      badge.textContent = st;
      tdSt.appendChild(badge);
      tr.appendChild(tdSt);

      // Ações
      const tdAct = document.createElement("td");
      const btns = document.createElement("div");
      btns.className = "btn-row";

      if (st === "done") {
        const d = parseJSON(row.result || "{}", {});
        if (d.filename_pdf && d.file_path_pdf) {
          const bPdf = document.createElement("button");
          bPdf.className = "btn small";
          bPdf.textContent = "PDF";
          bPdf.onclick = async () => {
            const r = await fetch('../submissions/' + row.id + '/download/pdf', { method: 'POST' });
            if (!r.ok) return alert('Falha no download (PDF).');
            const blob = await r.blob();
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = d.filename_pdf || ('dfd_' + row.id + '.pdf');
            a.click();
            URL.revokeObjectURL(a.href);
          };
          btns.appendChild(bPdf);
        }
        const bDocx = document.createElement("button");
        bDocx.className = "btn secondary small";
        bDocx.textContent = "DOCX";
        bDocx.onclick = async () => {
          const r = await fetch('../submissions/' + row.id + '/download/docx', { method: 'POST' });
          if (!r.ok) return alert('Falha no download (DOCX).');
          const blob = await r.blob();
          const a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          a.download = (d.filename_docx || ('dfd_' + row.id + '.docx'));
          a.click();
          URL.revokeObjectURL(a.href);
        };
        btns.appendChild(bDocx);
      } else {
        const span = document.createElement("span");
        span.className = "muted";
        span.textContent = "Processando…";
        btns.appendChild(span);
      }

      tdAct.appendChild(btns);
      tr.appendChild(tdAct);

      tbody.appendChild(tr);
    }
  }

  function applyFilterAndSort() {
    const term = (q.value || "").trim().toLowerCase();
    const sorter = sortSel.value;

    // filtro
    filtered = items.filter(row => {
      const num = rowNumero(row).toLowerCase();
      const ass = buildAssuntoFrom(row).toLowerCase();
      return !term || num.includes(term) || ass.includes(term);
    });

    // ordenação
    filtered.sort((a, b) => {
      if (sorter === "date_desc" || sorter === "date_asc") {
        const da = rowDate(a).getTime();
        const db = rowDate(b).getTime();
        return sorter === "date_desc" ? (db - da) : (da - db);
      }
      const na = rowNumero(a);
      const nb = rowNumero(b);
      return sorter === "numero_desc"
        ? nb.localeCompare(na, 'pt-BR', { numeric: true, sensitivity: 'base' })
        : na.localeCompare(nb, 'pt-BR', { numeric: true, sensitivity: 'base' });
    });

    renderTable();
  }

  async function fetchPage({ reset=false } = {}) {
    if (loading || end) return;
    loading = true;
    try {
      if (reset) {
        items = [];
        offset = 0;
        end = false;
      }
      const r = await fetch(`../submissions?limit=${limit}&offset=${offset}`);
      if (!r.ok) return;
      const data = await r.json();
      const rows = (data && data.items) || [];
      items = items.concat(rows);
      offset += rows.length;
      if (rows.length < limit) end = true;
      applyFilterAndSort();
      btnMore.disabled = end;
      btnMore.textContent = end ? "Fim da lista" : "Carregar mais";
    } finally {
      loading = false;
    }
  }

  // eventos
  btnMore.addEventListener('click', (e) => { e.preventDefault(); fetchPage(); });
  btnRefresh.addEventListener('click', (e) => { e.preventDefault(); fetchPage({ reset:true }); });
  q.addEventListener('input', () => { applyFilterAndSort(); });
  sortSel.addEventListener('change', () => { applyFilterAndSort(); });

  // init
  fetchPage({ reset:true });
</script>
"""
    return HTMLResponse(html)
