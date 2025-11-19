# apps/bff/app/automations/support.py
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.auth.rbac import require_roles_any
from app.db import add_audit, get_submission, insert_submission, list_submissions, update_submission

# --- PDF (opcional / guardado) ---
HAS_REPORTLAB = True
try:
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
except Exception:  # pragma: no cover
    HAS_REPORTLAB = False

logger = logging.getLogger(__name__)

# Perfis que podem baixar resultados/documentos (somente na página de Auditoria/Controle)
ALLOWED_AUDIT_ROLES = {"auditor", "admin", "controle"}


def _has_audit_role(user: Optional[Dict[str, Any]]) -> bool:
    roles = set((user or {}).get("roles") or [])
    return bool(roles & ALLOWED_AUDIT_ROLES)


router = APIRouter(
    prefix="/api/automations/support",
    tags=["automations", "support"],
    # Qualquer usuário autenticado pode abrir chamados; incluímos "controle"/"auditor" para permitir acesso ao módulo
    dependencies=[Depends(require_roles_any("user", "compras", "ferias", "coordenador", "admin", "controle", "auditor"))],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

CATALOG_FILE = Path(os.getenv("CATALOG_FILE", "/catalog/catalog.dev.json")).resolve()

SEVERITIES = [
    {"id": "none", "label": "Sem impacto"},
    {"id": "low", "label": "Baixo (contorna)"},
    {"id": "medium", "label": "Médio (atraso)"},
    {"id": "high", "label": "Alto (degrada processo)"},
    {"id": "blocker", "label": "Bloqueante (processo parado)"},
]

REPRO = [
    {"id": "always", "label": "Sempre"},
    {"id": "often", "label": "Frequentemente"},
    {"id": "sometimes", "label": "Às vezes"},
    {"id": "rarely", "label": "Raramente"},
    {"id": "once", "label": "Uma vez"},
    {"id": "untested", "label": "Não testado"},
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_load_catalog_blocks() -> List[Dict[str, str]]:
    """Lê o catálogo e retorna blocos visíveis {name, displayName, categoryId}."""
    try:
        data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
        blocks = data.get("blocks") or []
        out = []
        for b in blocks:
            if b.get("hidden"):
                continue
            out.append(
                {
                    "name": b.get("name") or "",
                    "displayName": b.get("displayName") or b.get("name") or "",
                    "categoryId": b.get("categoryId") or "",
                }
            )
        return [b for b in out if b["name"]]
    except Exception as e:
        logger.error("Falha ao ler catálogo '%s': %s", CATALOG_FILE, e)
        return []


class SupportPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    module: str = Field(..., min_length=2, description="Slug do módulo/bloco (ex.: dfd, ferias, fileshare)")
    summary: str = Field(..., min_length=8, max_length=160, description="Resumo breve do problema")
    description: str = Field(..., min_length=10, max_length=8000, description="Descrição detalhada (texto livre)")
    severity: str = Field(..., pattern="^(none|low|medium|high|blocker)$", description="Grau de impacto")
    reproducibility: str = Field("untested", pattern="^(always|often|sometimes|rarely|once|untested)$")
    steps_to_reproduce: Optional[str] = Field(None, max_length=4000)
    expected_result: Optional[str] = Field(None, max_length=2000)
    actual_result: Optional[str] = Field(None, max_length=2000)
    environment: Optional[str] = Field(None, max_length=1000, description="Navegador/SO/dispositivo/VPN")
    attachments: Optional[List[str]] = Field(default=None, description="URLs (ex.: Fileshare) ou tokens")
    contact_email: Optional[EmailStr] = Field(default=None)
    contact_phone: Optional[str] = Field(default=None, max_length=60)
    consent_contact: bool = Field(default=True)

    def normalized(self) -> Dict[str, Any]:
        d = self.model_dump()
        # Normalizações simples
        d["module"] = (d["module"] or "").strip().lower()
        d["summary"] = (d["summary"] or "").strip()
        d["severity"] = (d["severity"] or "").lower()
        d["reproducibility"] = (d["reproducibility"] or "untested").lower()
        if isinstance(d.get("attachments"), list):
            d["attachments"] = [a.strip() for a in d["attachments"] if a and str(a).strip()]
        return d


class SubmissionResponse(BaseModel):
    id: str
    status: str
    created_at: datetime


def _current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Compat: algumas rotas/middlewares usam request.session["user"] (login real),
    e outras podem povoar request.state.user. Aceitamos ambos.
    """
    return getattr(request.state, "user", None) or request.session.get("user")


@router.get("/schema")
def get_schema() -> JSONResponse:
    """Schema de UI (opções de módulo, severidades e reprodutibilidade)."""
    modules = _safe_load_catalog_blocks()
    return JSONResponse(
        {
            "kind": "support",
            "version": "1.0.0",
            "modules": modules,
            "severities": SEVERITIES,
            "reproducibility": REPRO,
            # dica opcional para UIs
            "capabilities": {"download_json": True, "document_pdf": True},
        }
    )


# --------------------------------------------------------------------
# UIs
#  - /ui           → UI técnica (já existente)
#  - /ui.html      → alias (para compatibilidade com botão/link)
#  - /padrao.html  → UI padrão para usuários comuns
# --------------------------------------------------------------------

@router.get("/ui")
def support_ui(request: Request) -> HTMLResponse:
    """Página HTML técnica (iframe) com formulário detalhado."""
    modules = _safe_load_catalog_blocks()
    return templates.TemplateResponse(
        "support/ui.html",
        {
            "request": request,
            "modules": modules,
            "severities": SEVERITIES,
            "repro": REPRO,
            # a UI técnica não exibe botões de download nesta tela
            "show_downloads": False,
        },
    )


@router.get("/ui.html")
def support_ui_html_alias(request: Request) -> HTMLResponse:
    """
    Alias com sufixo .html da UI técnica.
    Útil para navegação a partir do botão no canto superior direito da UI padrão.
    """
    return support_ui(request)


@router.get("/padrao.html")
def support_ui_padrao(request: Request) -> HTMLResponse:
    """
    UI padrão (usuários comuns) — formulário simplificado.
    O template deve exibir um botão no canto superior direito que redireciona para /ui.html.
    """
    # A UI padrão normalmente não precisa de 'modules/severities/repro',
    # mas deixamos disponível caso o template queira sugerir módulo ou metadados.
    modules = _safe_load_catalog_blocks()
    return templates.TemplateResponse(
        "support/padrao.html",
        {
            "request": request,
            "modules": modules,
            "severities": SEVERITIES,
            "repro": REPRO,
            "show_downloads": False,
            # Hints para o template controlar navegação entre UIs
            "go_tech_href": "/api/automations/support/ui.html",
        },
    )


# ------------------------- Utils de serialização segura -------------------------
def _coerce_jsonable(obj: Any) -> Any:
    """
    Converte recursivamente valores não-serializáveis (datetime, bytes, etc.)
    para representações JSON-friendly.
    """
    if isinstance(obj, dict):
        return {k: _coerce_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_coerce_jsonable(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8")
        except Exception:
            return obj.hex()
    return obj


@router.post("/submit")
def submit_bug(request: Request, payload: SupportPayload, bg: BackgroundTasks) -> JSONResponse:
    """Cria uma submissão 'support' e já marca como 'done' (não há processamento assíncrono)."""
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    # Validação/normalização extra: módulo deve existir no catálogo atual (não bloqueante)
    modules = {m["name"] for m in _safe_load_catalog_blocks()}
    p = payload.normalized()
    if p["module"] not in modules:
        logger.warning("Módulo informado não existe no catálogo: %s", p["module"])

    # Gere o ID aqui para não depender do retorno do insert_submission()
    sub_id = str(uuid4())
    sub = {
        "id": sub_id,
        "kind": "support",
        "version": "1.0.0",
        "actor_cpf": user.get("cpf"),
        "actor_nome": user.get("nome") or user.get("name"),
        "actor_email": user.get("email"),
        "payload": p,
        "status": "queued",  # será atualizado para 'done' abaixo
        "result": None,
        "error": None,
    }
    try:
        insert_submission(sub)
        # Auditoria compatível com o Controle (usa 'sid')
        add_audit("support", "submitted", user, {"sid": sub_id, "summary": p.get("summary"), "module": p.get("module")})
        # Como não há processamento, marca como 'done' e audita 'completed'
        update_submission(sub_id, status="done", error=None)
        add_audit("support", "completed", user, {"sid": sub_id})
    except Exception as e:
        logger.exception("Falha ao inserir/atualizar submission support: %s", e)
        raise HTTPException(status_code=500, detail="failed to create submission")

    # Futuro: enviar notificação (e-mail/Teams) em tarefa de fundo
    # bg.add_task(...)

    return JSONResponse({"id": sub_id, "status": "done"})


@router.get("/submissions")
def my_submissions(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    """Lista submissões do próprio usuário (seguras por CPF/e-mail)."""
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    rows = list_submissions(
        kind="support",
        actor_cpf=user.get("cpf"),
        actor_email=user.get("email"),
        limit=limit,
        offset=offset,
    )
    return rows


@router.get("/submissions/{id}")
def get_my_submission(id: str, request: Request) -> Dict[str, Any]:
    """Detalhe de uma submissão do próprio usuário."""
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    sub = get_submission(id)
    if not sub:
        raise HTTPException(status_code=404, detail="submission not found")
    # Segurança: só permite acessar o próprio (basta 1 divergência para bloquear)
    if ((sub.get("actor_cpf") and user.get("cpf") and sub["actor_cpf"] != user["cpf"]) or
        (sub.get("actor_email") and user.get("email") and sub["actor_email"] != user["email"])):
        raise HTTPException(status_code=403, detail="forbidden")
    return sub


# -------------------------
# Download da submissão (JSON "bonito")
#   - Somente via POST
#   - Restrito a perfis de Auditoria/Controle
#   - GET -> 405 com mensagem clara
# -------------------------

@router.post(
    "/submissions/{id}/download",
    dependencies=[Depends(require_roles_any(*ALLOWED_AUDIT_ROLES))],
)
def download_submission(id: str, request: Request) -> StreamingResponse:
    """
    Baixa o JSON 'bonito' da submissão.
    Política: apenas papéis de Auditoria/Controle podem baixar (independente do autor).
    """
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    if not _has_audit_role(user):
        raise HTTPException(
            status_code=403,
            detail="Download permitido apenas para Auditoria/Controle.",
        )

    sub = get_submission(id)
    if not sub:
        raise HTTPException(status_code=404, detail="submission not found")

    safe = _coerce_jsonable(sub)
    data = json.dumps(safe, ensure_ascii=False, indent=2).encode("utf-8")
    add_audit("support", "download_json", user, {"sid": id})
    return StreamingResponse(
        content=iter([data]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="support-{id}.json"'},
    )


@router.get("/submissions/{id}/download")
def download_submission_get_not_allowed() -> None:
    # GET propositalmente não permitido (evita clique em link na aba Suporte)
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Use POST para download e apenas a partir da página de Auditoria/Controle.",
    )


# ------------------------------------------------------------
# Documento do relato (PDF via ReportLab) — também restrito
# ------------------------------------------------------------
def _severity_label(sev_id: str) -> str:
    for s in SEVERITIES:
        if s["id"] == (sev_id or "").lower():
            return s["label"]
    return sev_id or ""


def _repro_label(rep_id: str) -> str:
    for r in REPRO:
        if r["id"] == (rep_id or "").lower():
            return r["label"]
    return rep_id or ""


def _build_support_pdf(sub: Dict[str, Any]) -> bytes:
    if not HAS_REPORTLAB:  # pragma: no cover
        raise RuntimeError("reportlab not installed")

    payload = sub.get("payload") or {}
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Relato de Suporte & Feedback",
        author=str(sub.get("actor_nome") or ""),
    )
    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h1.fontSize = 16
    h1.spaceAfter = 6
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, textColor=colors.grey, spaceAfter=6)
    label = ParagraphStyle("label", parent=styles["Normal"], fontSize=10, textColor=colors.grey, spaceAfter=2)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=11, leading=14, spaceAfter=10)

    story: List[Any] = []
    story.append(Paragraph("Suporte & Feedback — Relato", h1))
    meta_rows = [
        ["ID", sub.get("id") or ""],
        ["Data/Hora", str(sub.get("created_at") or "")],
        ["Status", sub.get("status") or ""],
        ["Módulo", payload.get("module") or ""],
        ["Gravidade", _severity_label(payload.get("severity") or "")],
        ["Reprodutibilidade", _repro_label(payload.get("reproducibility") or "")],
        ["Ambiente", payload.get("environment") or ""],
        ["Autor", f'{sub.get("actor_nome") or ""} <{sub.get("actor_email") or ""}> CPF: {sub.get("actor_cpf") or ""}'],
    ]
    meta_tbl = Table(meta_rows, colWidths=[32 * mm, 138 * mm])
    meta_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.grey),
                ("BOX", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
            ]
        )
    )
    story.append(meta_tbl)
    story.append(Spacer(1, 6))
    story.append(Paragraph("Este documento resume as informações fornecidas no relato e pode ser anexado à auditoria do processo.", small))

    def section(title: str, value: str):
        if not value:
            return
        story.append(Paragraph(title, label))
        story.append(Paragraph((value or "").replace("\n", "<br/>"), body))

    section("Resumo", payload.get("summary") or "")
    section("Descrição", payload.get("description") or "")
    section("Passos para reproduzir", payload.get("steps_to_reproduce") or "")
    section("Resultado esperado", payload.get("expected_result") or "")
    section("Resultado obtido", payload.get("actual_result") or "")
    links = payload.get("attachments") or []
    if isinstance(links, list) and links:
        section("Anexos/Links", "<br/>".join(links))
    contact = []
    if payload.get("contact_email"):
        contact.append(f'Email: {payload.get("contact_email")}')
    if payload.get("contact_phone"):
        contact.append(f'Telefone: {payload.get("contact_phone")}')
    if contact:
        section("Contato", " — ".join(contact))
    section("Consentimento de contato", "Sim" if payload.get("consent_contact") else "Não")

    doc.build(story)
    buf.seek(0)
    return buf.read()


@router.post(
    "/submissions/{id}/document",
    dependencies=[Depends(require_roles_any(*ALLOWED_AUDIT_ROLES))],
)
def download_submission_document(
    id: str,
    request: Request,
    fmt: str = Query("pdf", pattern="^(pdf)$"),
) -> StreamingResponse:
    """
    Gera um documento do relato (apenas Auditoria/Controle):
      - fmt=pdf → PDF (ReportLab)
    """
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    if not _has_audit_role(user):
        raise HTTPException(
            status_code=403,
            detail="Geração de documento permitida apenas para Auditoria/Controle.",
        )

    sub = get_submission(id)
    if not sub:
        raise HTTPException(status_code=404, detail="submission not found")

    if fmt == "pdf":
        if not HAS_REPORTLAB:  # pragma: no cover
            raise HTTPException(status_code=501, detail="pdf generation not available (install reportlab)")
        try:
            pdf_bytes = _build_support_pdf(sub)
        except Exception as e:  # pragma: no cover
            logger.exception("Falha ao gerar PDF do suporte %s: %s", id, e)
            raise HTTPException(status_code=500, detail="failed to generate pdf")
        # audita a geração do documento
        add_audit("support", "document_pdf", user, {"sid": id})
        return StreamingResponse(
            content=iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="support-{id}.pdf"'},
        )

    raise HTTPException(status_code=400, detail="unsupported format")


@router.get("/submissions/{id}/document")
def document_get_not_allowed() -> None:
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Use POST para gerar/baixar documentos e apenas a partir da página de Auditoria/Controle.",
    )
