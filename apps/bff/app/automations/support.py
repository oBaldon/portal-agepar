# apps/bff/app/automations/support.py
"""
Módulo da automação "support" (Suporte & Feedback).

Propósito
---------
Registrar relatos de suporte/feedback dos usuários, expor UIs de envio,
persistir as submissões no repositório do BFF, permitir consulta segura
pelo próprio autor e disponibilizar, para perfis de Auditoria/Controle,
o download do JSON "bonito" e a geração de um documento PDF do relato.

RBAC / Segurança
----------------
- O `router` exige autenticação e, por padrão, qualquer papel listado em
  `require_roles_any("user", "compras", "ferias", "coordenador", "admin", "controle", "auditor")`.
- Endpoints sensíveis (download de JSON e geração de documento) são
  restritos aos papéis em `ALLOWED_AUDIT_ROLES` e ainda validam via `_has_audit_role`.
- As consultas de submissões por ID garantem ownership comparando CPF/e-mail.

Efeitos colaterais
------------------
- Acesso ao módulo `app.db` para inserir/atualizar/consultar submissões
  e registrar auditoria (`insert_submission`, `update_submission`,
  `get_submission`, `list_submissions`, `add_audit`).
- Leitura de arquivo de catálogo para montar sugestões de módulos.
- Geração de PDF (opcional) via ReportLab, quando instalado.

Exemplos
--------
- Envio (POST /api/automations/support/submit):
    Corpo JSON compatível com `SupportPayload`.
- Download JSON (POST /api/automations/support/submissions/{id}/download):
    Requer papel em Auditoria/Controle.
- Documento PDF (POST /api/automations/support/submissions/{id}/document?fmt=pdf):
    Requer papel em Auditoria/Controle e ReportLab instalado.
"""

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

HAS_REPORTLAB = True
try:
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
except Exception:
    HAS_REPORTLAB = False

logger = logging.getLogger(__name__)

ALLOWED_AUDIT_ROLES = {"auditor", "admin", "controle"}


def _has_audit_role(user: Optional[Dict[str, Any]]) -> bool:
    """
    Verifica se o usuário possui um dos papéis autorizados para auditoria.

    Parâmetros
    ----------
    user : Optional[Dict[str, Any]]
        Objeto de usuário (tipicamente oriundo da sessão).

    Retorna
    -------
    bool
        True se contiver algum papel em `ALLOWED_AUDIT_ROLES`.
    """
    roles = set((user or {}).get("roles") or [])
    return bool(roles & ALLOWED_AUDIT_ROLES)


router = APIRouter(
    prefix="/api/automations/support",
    tags=["automations", "support"],
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
    """
    Obtém o timestamp atual em UTC.

    Retorna
    -------
    datetime
        Data/hora com timezone UTC.
    """
    return datetime.now(timezone.utc)


def _safe_load_catalog_blocks() -> List[Dict[str, str]]:
    """
    Lê o catálogo de módulos e retorna blocos visíveis.

    Retorna
    -------
    List[Dict[str, str]]
        Lista de objetos com chaves: name, displayName, categoryId.

    Observações
    -----------
    Em caso de erro de leitura/parse, retorna lista vazia e loga o problema.
    """
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
    """
    Modelo de entrada para relatos de suporte/feedback.

    Atributos
    ---------
    module : str
        Slug do módulo/bloco (ex.: 'dfd', 'ferias', 'fileshare').
    summary : str
        Resumo breve do problema.
    description : str
        Descrição detalhada do problema.
    severity : str
        Gravidade: none|low|medium|high|blocker.
    reproducibility : str
        Frequência: always|often|sometimes|rarely|once|untested.
    steps_to_reproduce : Optional[str]
        Passos para reproduzir.
    expected_result : Optional[str]
        Resultado esperado.
    actual_result : Optional[str]
        Resultado obtido.
    environment : Optional[str]
        Informações de ambiente (navegador/SO/dispositivo/VPN).
    attachments : Optional[List[str]]
        URLs ou tokens de anexos (ex.: Fileshare).
    contact_email : Optional[EmailStr]
        E-mail para contato.
    contact_phone : Optional[str]
        Telefone para contato.
    consent_contact : bool
        Indica consentimento para contato de retorno.
    """
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
        """
        Retorna um dicionário normalizado para persistência.

        Retorna
        -------
        Dict[str, Any]
            Campos sanitizados (lowercase para enums, trimming, anexos filtrados).
        """
        d = self.model_dump()
        d["module"] = (d["module"] or "").strip().lower()
        d["summary"] = (d["summary"] or "").strip()
        d["severity"] = (d["severity"] or "").lower()
        d["reproducibility"] = (d["reproducibility"] or "untested").lower()
        if isinstance(d.get("attachments"), list):
            d["attachments"] = [a.strip() for a in d["attachments"] if a and str(a).strip()]
        return d


class SubmissionResponse(BaseModel):
    """
    Resposta curta de submissão.

    Atributos
    ---------
    id : str
        Identificador da submissão.
    status : str
        Status atual da submissão.
    created_at : datetime
        Data/hora de criação.
    """
    id: str
    status: str
    created_at: datetime


def _current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Obtém o usuário autenticado da requisição.

    Parâmetros
    ----------
    request : Request
        Requisição corrente.

    Retorna
    -------
    Optional[Dict[str, Any]]
        Usuário da sessão (state.user ou session['user']), se presente.
    """
    return getattr(request.state, "user", None) or request.session.get("user")


@router.get("/schema")
def get_schema() -> JSONResponse:
    """
    Retorna o schema informativo para a UI de suporte.

    Retorna
    -------
    JSONResponse
        Objeto com: kind, version, modules, severities, reproducibility, capabilities.
    """
    modules = _safe_load_catalog_blocks()
    return JSONResponse(
        {
            "kind": "support",
            "version": "1.0.0",
            "modules": modules,
            "severities": SEVERITIES,
            "reproducibility": REPRO,
            "capabilities": {"download_json": True, "document_pdf": True},
        }
    )


@router.get("/ui")
def support_ui(request: Request) -> HTMLResponse:
    """
    UI técnica (iframe) com formulário detalhado.

    Parâmetros
    ----------
    request : Request

    Retorna
    -------
    HTMLResponse
        Template 'support/ui.html'.
    """
    modules = _safe_load_catalog_blocks()
    return templates.TemplateResponse(
        "support/ui.html",
        {
            "request": request,
            "modules": modules,
            "severities": SEVERITIES,
            "repro": REPRO,
            "show_downloads": False,
        },
    )


@router.get("/ui.html")
def support_ui_html_alias(request: Request) -> HTMLResponse:
    """
    Alias da UI técnica com sufixo '.html'.

    Parâmetros
    ----------
    request : Request

    Retorna
    -------
    HTMLResponse
        Template da UI técnica.
    """
    return support_ui(request)


@router.get("/padrao.html")
def support_ui_padrao(request: Request) -> HTMLResponse:
    """
    UI padrão para usuários (formulário mais simples).

    Parâmetros
    ----------
    request : Request

    Retorna
    -------
    HTMLResponse
        Template 'support/padrao.html'.
    """
    modules = _safe_load_catalog_blocks()
    return templates.TemplateResponse(
        "support/padrao.html",
        {
            "request": request,
            "modules": modules,
            "severities": SEVERITIES,
            "repro": REPRO,
            "show_downloads": False,
            "go_tech_href": "/api/automations/support/ui.html",
        },
    )


def _coerce_jsonable(obj: Any) -> Any:
    """
    Converte recursivamente valores não serializáveis para estruturas JSON-amigáveis.

    Parâmetros
    ----------
    obj : Any
        Valor de entrada potencialmente não-serializável.

    Retorna
    -------
    Any
        Estrutura equivalente serializável (datetime → ISO, bytes → UTF-8/hex, etc.).
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
    """
    Cria uma submissão de suporte e finaliza imediatamente (sem processamento assíncrono).

    Parâmetros
    ----------
    request : Request
        Usada para extrair o usuário autenticado.
    payload : SupportPayload
        Relato de suporte/feedback.
    bg : BackgroundTasks
        Tarefas de fundo (reservado para notificações futuras).

    Retorna
    -------
    JSONResponse
        {'id': str, 'status': 'done'}

    Exceções
    --------
    401 Unauthorized
        Usuário não autenticado.
    500 Internal Server Error
        Falha ao inserir/atualizar a submissão.
    """
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    modules = {m["name"] for m in _safe_load_catalog_blocks()}
    p = payload.normalized()
    if p["module"] not in modules:
        logger.warning("Módulo informado não existe no catálogo: %s", p["module"])

    sub_id = str(uuid4())
    sub = {
        "id": sub_id,
        "kind": "support",
        "version": "1.0.0",
        "actor_cpf": user.get("cpf"),
        "actor_nome": user.get("nome") or user.get("name"),
        "actor_email": user.get("email"),
        "payload": p,
        "status": "queued",
        "result": None,
        "error": None,
    }
    try:
        insert_submission(sub)
        add_audit("support", "submitted", user, {"sid": sub_id, "summary": p.get("summary"), "module": p.get("module")})
        update_submission(sub_id, status="done", error=None)
        add_audit("support", "completed", user, {"sid": sub_id})
    except Exception as e:
        logger.exception("Falha ao inserir/atualizar submission support: %s", e)
        raise HTTPException(status_code=500, detail="failed to create submission")

    return JSONResponse({"id": sub_id, "status": "done"})


@router.get("/submissions")
def my_submissions(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> List[Dict[str, Any]]:
    """
    Lista submissões do próprio usuário (por CPF/e-mail).

    Parâmetros
    ----------
    request : Request
    limit : int
    offset : int

    Retorna
    -------
    List[Dict[str, Any]]
        Submissões visíveis ao autor.

    Exceções
    --------
    401 Unauthorized
        Usuário não autenticado.
    """
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
    """
    Detalha uma submissão do próprio usuário.

    Parâmetros
    ----------
    id : str
        Identificador da submissão.
    request : Request

    Retorna
    -------
    Dict[str, Any]
        Registro completo da submissão.

    Exceções
    --------
    401 Unauthorized
        Usuário não autenticado.
    404 Not Found
        Submissão inexistente.
    403 Forbidden
        Submissão não pertence ao usuário.
    """
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    sub = get_submission(id)
    if not sub:
        raise HTTPException(status_code=404, detail="submission not found")
    if ((sub.get("actor_cpf") and user.get("cpf") and sub["actor_cpf"] != user["cpf"]) or
        (sub.get("actor_email") and user.get("email") and sub["actor_email"] != user["email"])):
        raise HTTPException(status_code=403, detail="forbidden")
    return sub


@router.post(
    "/submissions/{id}/download",
    dependencies=[Depends(require_roles_any(*ALLOWED_AUDIT_ROLES))],
)
def download_submission(id: str, request: Request) -> StreamingResponse:
    """
    Download do JSON "bonito" da submissão (somente Auditoria/Controle).

    Parâmetros
    ----------
    id : str
        Identificador da submissão.
    request : Request

    Retorna
    -------
    StreamingResponse
        Conteúdo JSON com indentação para auditoria.

    Exceções
    --------
    401 Unauthorized
        Usuário não autenticado.
    403 Forbidden
        Usuário sem papel de Auditoria/Controle.
    404 Not Found
        Submissão inexistente.
    """
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    if not _has_audit_role(user):
        raise HTTPException(status_code=403, detail="Download permitido apenas para Auditoria/Controle.")

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
    """
    Método não permitido para download.

    Exceções
    --------
    405 Method Not Allowed
        Instrui o cliente a utilizar POST.
    """
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Use POST para download e apenas a partir da página de Auditoria/Controle.",
    )


def _severity_label(sev_id: str) -> str:
    """
    Resolve o rótulo legível de severidade.

    Parâmetros
    ----------
    sev_id : str
        Identificador (none|low|medium|high|blocker).

    Retorna
    -------
    str
        Rótulo em português ou o próprio identificador.
    """
    for s in SEVERITIES:
        if s["id"] == (sev_id or "").lower():
            return s["label"]
    return sev_id or ""


def _repro_label(rep_id: str) -> str:
    """
    Resolve o rótulo legível de reprodutibilidade.

    Parâmetros
    ----------
    rep_id : str
        Identificador (always|often|sometimes|rarely|once|untested).

    Retorna
    -------
    str
        Rótulo em português ou o próprio identificador.
    """
    for r in REPRO:
        if r["id"] == (rep_id or "").lower():
            return r["label"]
    return rep_id or ""


def _build_support_pdf(sub: Dict[str, Any]) -> bytes:
    """
    Gera o PDF do relato usando ReportLab.

    Parâmetros
    ----------
    sub : Dict[str, Any]
        Submissão completa (payload + metadados).

    Retorna
    -------
    bytes
        Conteúdo do PDF.

    Exceções
    --------
    RuntimeError
        Quando o ReportLab não está instalado.
    """
    if not HAS_REPORTLAB:
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

    def section(title: str, value: str) -> None:
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
    Gera e baixa o documento do relato (somente Auditoria/Controle).

    Parâmetros
    ----------
    id : str
        Identificador da submissão.
    request : Request
    fmt : str
        Formato solicitado (atualmente apenas 'pdf').

    Retorna
    -------
    StreamingResponse
        PDF com o conteúdo do relato.

    Exceções
    --------
    401 Unauthorized
        Usuário não autenticado.
    403 Forbidden
        Usuário sem papel de Auditoria/Controle.
    404 Not Found
        Submissão inexistente.
    501 Not Implemented
        ReportLab ausente para geração de PDF.
    500 Internal Server Error
        Falha ao gerar o documento.
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
        if not HAS_REPORTLAB:
            raise HTTPException(status_code=501, detail="pdf generation not available (install reportlab)")
        try:
            pdf_bytes = _build_support_pdf(sub)
        except Exception as e:
            logger.exception("Falha ao gerar PDF do suporte %s: %s", id, e)
            raise HTTPException(status_code=500, detail="failed to generate pdf")
        add_audit("support", "document_pdf", user, {"sid": id})
        return StreamingResponse(
            content=iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="support-{id}.pdf"'},
        )

    raise HTTPException(status_code=400, detail="unsupported format")


@router.get("/submissions/{id}/document")
def document_get_not_allowed() -> None:
    """
    Método não permitido para geração de documento.

    Exceções
    --------
    405 Method Not Allowed
        Instrui o cliente a utilizar POST.
    """
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Use POST para gerar/baixar documentos e apenas a partir da página de Auditoria/Controle.",
    )
