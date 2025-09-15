from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends
from starlette.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field, ConfigDict, ValidationError, field_validator, model_validator
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
DFD_VERSION = "2.2.0"  # alinhado à UI com itens antes dos campos gerais finais
REQUIRED_ROLES = ("automations.dfd",)

# Diretório com os modelos DOCX por diretoria (timbre)
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
    """Aceita dict/list/str/bytes; retorna dict/list (robusto a SQLite/Postgres)."""
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


# ---------------------- Models & Validation ----------------------
MAX_ASSUNTO_LEN = 200
MAX_TEXTO_LONGO = 8000

ALLOWED_UNIDADES = {
    "Caixa","Caloria","Cartela","Cartucho","Dose","Dúzia","Frasco","Grama","Kit","Litro","Mês","Metro",
    "Metro cúbico","Metro linear","Metro quadrado","Milheiro","Miligrama","Mililitro","Outras Unidades de Medidas",
    "Par","Quilograma","Quilograma do peso drenado","Quilômetro","Rolo","Teste","Tubo","Unidade Internacional","Unitário"
}
ALLOWED_PRIORIDADE = {
    "Alto, quando a impossibilidade de contratação provoca interrupção de processo crítico ou estratégico.",
    "Médio, quando a impossibilidade de contratação provoca atraso de processo crítico ou estratégico.",
    "Baixo, quando a impossibilidade de contratação provoca interrupção ou atraso de processo não crítico.",
    "Muito baixo, quando a continuidade do processo é possível mediante o emprego de uma solução de contorno."
}
ALLOWED_SIMNAO = {"Sim", "Não"}
MESES = ["janeiro","fevereiro","março","abril","maio","junho","julho","agosto","setembro","outubro","novembro","dezembro"]
REGEX_DATA_PRETENDIDA = re.compile(
    r"^(janeiro|fevereiro|março|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro) de (\d{4})$"
)


class Item(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    # Itens (por UI atual)
    descricao: str = Field("", max_length=MAX_TEXTO_LONGO)
    haDependencia: str  # "Sim" | "Não"
    dependenciaQual: Optional[str] = Field(default=None, max_length=MAX_TEXTO_LONGO)
    renovacaoContrato: str  # "Sim" | "Não"
    quantidade: int = Field(0, ge=0)
    unidadeMedida: str
    valorUnitario: float = Field(0.0, ge=0.0)
    valorTotal: Optional[float] = Field(None, ge=0.0)

    @field_validator("unidadeMedida")
    @classmethod
    def _valid_um(cls, v: str) -> str:
        if v and v in ALLOWED_UNIDADES:
            return v
        raise ValueError("Unidade de medida inválida.")

    @field_validator("haDependencia", "renovacaoContrato")
    @classmethod
    def _valid_simnao(cls, v: str) -> str:
        if v and v in ALLOWED_SIMNAO:
            return v
        raise ValueError("Valor deve ser 'Sim' ou 'Não'.")

    @model_validator(mode="after")
    def _normalize_compute(self):
        # Dependência: se Sim, exige 'dependenciaQual'
        if self.haDependencia == "Sim" and not (self.dependenciaQual or "").strip():
            raise ValueError("Campo 'Se Sim, descreva o vínculo' é obrigatório quando há vínculo.")
        # Valor total sempre recalculado
        try:
            qt = int(self.quantidade or 0)
            vu = float(self.valorUnitario or 0.0)
        except Exception:
            qt, vu = 0, 0.0
        self.valorTotal = round(qt * vu, 2)
        return self


class DfdIn(BaseModel):
    """Modelo de entrada do DFD (alinhado à nova UI)."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    # Cabeçalho
    modelo_slug: str = Field(..., alias="modeloSlug")  # pasta do timbre
    numero: str
    assunto: str = Field(..., min_length=1, max_length=MAX_ASSUNTO_LEN)  # compõe o assunto final
    pca_ano: str = Field(..., alias="pcaAno", pattern=r"^\d{4}$")

    # Bloco geral (unificado)
    diretoria_demandante: str = Field(..., alias="diretoriaDemandante")
    alinhamento_pe: Optional[str] = Field("", alias="alinhamentoPE", max_length=MAX_TEXTO_LONGO)
    justificativa_necessidade: Optional[str] = Field("", alias="justificativaNecessidade", max_length=MAX_TEXTO_LONGO)
    objeto: str = Field(..., min_length=1, max_length=MAX_TEXTO_LONGO)

    # Campos gerais finais (após itens na UI)
    prazos_envolvidos: Optional[str] = Field("", alias="prazosEnvolvidos")
    consequencia_nao_aquisicao: Optional[str] = Field("", alias="consequenciaNaoAquisicao", max_length=MAX_TEXTO_LONGO)
    grau_prioridade: Optional[str] = Field(None, alias="grauPrioridade")

    # Itens
    items: List[Item] = Field(..., min_length=1)

    @field_validator("grau_prioridade")
    @classmethod
    def _valid_prioridade_geral(cls, v: Optional[str]) -> Optional[str]:
        if v in (None, ""):
            return ""
        if v in ALLOWED_PRIORIDADE:
            return v
        raise ValueError("Grau de prioridade inválido.")

    @field_validator("prazos_envolvidos")
    @classmethod
    def _valid_prazos_fmt(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return ""
        if not REGEX_DATA_PRETENDIDA.match(v.strip()):
            raise ValueError("Use o formato 'mês de AAAA' (em minúsculas).")
        return v

    @model_validator(mode="after")
    def _valid_relacoes(self):
        # Se prazos_envolvidos vier preenchido, o ano deve bater com pca_ano
        if self.prazos_envolvidos:
            m = REGEX_DATA_PRETENDIDA.match(self.prazos_envolvidos.strip())
            if not m:
                raise ValueError("Campo 'Prazos envolvidos' inválido.")
            ano_prazo = m.group(2)
            if ano_prazo != (self.pca_ano or "").strip():
                raise ValueError(f"'Prazos envolvidos' deve estar no ano do PCA ({self.pca_ano}).")
        return self


SCHEMA = {
    "title": "DFD — Documento de Formalização da Demanda (MVP)",
    "version": DFD_VERSION,
    "fields": [
        {"name": "modeloSlug", "type": "select", "label": "Timbre"},
        {"name": "numero", "type": "text", "label": "Nº do Memorando"},
        {"name": "assunto", "type": "text", "label": "Assunto"},
        {"name": "pcaAno", "type": "text", "label": "Ano de execução do PCA"},
        {"name": "diretoriaDemandante", "type": "select", "label": "Diretoria demandante"},
        {"name": "alinhamentoPE", "type": "textarea", "label": "Alinhamento com o Planejamento Estratégico"},
        {"name": "justificativaNecessidade", "type": "textarea", "label": "Justificativa da necessidade"},
        {"name": "objeto", "type": "textarea", "label": "Objeto"},

        # === Itens agora vêm antes dos campos gerais finais ===
        {"name": "items", "type": "array", "label": "Itens"},

        # Campos gerais finais (após Itens)
        {"name": "prazosEnvolvidos", "type": "select", "label": "Prazos envolvidos"},
        {"name": "consequenciaNaoAquisicao", "type": "textarea", "label": "Consequência da não aquisição"},
        {"name": "grauPrioridade", "type": "select", "label": "Grau de prioridade"},
    ],
}

# Mapeamento amigável de campos → rótulos (para mensagens de validação)
FIELD_INFO: Dict[str, Dict[str, Any]] = {
    "modeloSlug": {"label": "Timbre"},
    "modelo_slug": {"label": "Timbre"},
    "numero": {"label": "Nº do Memorando"},
    "assunto": {"label": "Assunto", "max_length": MAX_ASSUNTO_LEN, "min_length": 1},
    "pcaAno": {"label": "Ano de execução do PCA", "pattern": r"^\d{4}$"},
    "pca_ano": {"label": "Ano de execução do PCA", "pattern": r"^\d{4}$"},
    "diretoriaDemandante": {"label": "Diretoria demandante"},
    "diretoria_demandante": {"label": "Diretoria demandante"},
    "alinhamentoPE": {"label": "Alinhamento com o Planejamento Estratégico", "max_length": MAX_TEXTO_LONGO},
    "alinhamento_pe": {"label": "Alinhamento com o Planejamento Estratégico", "max_length": MAX_TEXTO_LONGO},
    "justificativaNecessidade": {"label": "Justificativa da necessidade", "max_length": MAX_TEXTO_LONGO},
    "justificativa_necessidade": {"label": "Justificativa da necessidade", "max_length": MAX_TEXTO_LONGO},
    "objeto": {"label": "Objeto", "max_length": MAX_TEXTO_LONGO, "min_length": 1},
    "prazosEnvolvidos": {"label": "Prazos envolvidos"},
    "prazos_envolvidos": {"label": "Prazos envolvidos"},
    "consequenciaNaoAquisicao": {"label": "Consequência da não aquisição", "max_length": MAX_TEXTO_LONGO},
    "consequencia_nao_aquisicao": {"label": "Consequência da não aquisição", "max_length": MAX_TEXTO_LONGO},
    "grauPrioridade": {"label": "Grau de prioridade"},
    "grau_prioridade": {"label": "Grau de prioridade"},
    # Itens
    "descricao": {"label": "Descrição sucinta do objeto"},
    "haDependencia": {"label": "Há vinculação ou dependência com a contratação de outro item?"},
    "dependenciaQual": {"label": "Se 'Sim', descreva o vínculo"},
    "renovacaoContrato": {"label": "Renovação de contrato"},
    "unidadeMedida": {"label": "Unidade de medida"},
    "quantidade": {"label": "Quantidade a ser adquirida"},
    "valorUnitario": {"label": "Estimativa de valor unitário (R$)"},
    "valorTotal": {"label": "Estimativa de valor total (auto)"},
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
            # Para erros de model_validator/field_validator:
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

        # Monta ASSUNTO final: "DFD - PCA <ano> - <assunto>"
        assunto_bruto = (raw.get("assunto") or "").strip()
        pca_ano = (raw.get("pcaAno") or "").strip()
        assunto_final = f"DFD - PCA {pca_ano} - {assunto_bruto}"

        # Normaliza itens e total geral (confere total no backend)
        itens_in = list(raw.get("items") or [])
        itens_out: List[Dict[str, Any]] = []
        total_geral = 0.0
        for i, it in enumerate(itens_in, start=1):
            try:
                item = Item(**it)  # revalida item com regras de negócio
                item_dict = item.model_dump()
            except ValidationError as ve:
                # Erro amigável por item
                update_submission(sid, status="error", error=f"Item {i}: {ve.errors()}")
                add_audit(KIND, "failed", actor, {"sid": sid, "error": f"item {i} invalid"})
                return
            total_geral += float(item_dict.get("valorTotal") or 0.0)
            itens_out.append(item_dict)

        ctx = {
            "diretoria": raw["modeloSlug"],
            "numero": raw["numero"],
            "assunto": assunto_final,  # usado no cabeçalho/timbre
            "pca_ano": pca_ano,        # usado no texto introdutório do corpo
            "data": today_iso,
            # campos gerais
            "diretoria_demandante": raw.get("diretoriaDemandante") or "",
            "alinhamento_pe": raw.get("alinhamentoPE") or "",
            "justificativa_necessidade": raw.get("justificativaNecessidade") or "",
            "objeto": raw.get("objeto") or "",
            # campos gerais finais
            "prazos_envolvidos": raw.get("prazosEnvolvidos") or "",
            "consequencia_nao_aquisicao": raw.get("consequenciaNaoAquisicao") or "",
            "grau_prioridade": raw.get("grauPrioridade") or "",
            # itens e totais
            "itens": itens_out,
            "total_geral": round(total_geral, 2),
        }

        # Log de placeholders (apenas informativo)
        try:
            placeholders = get_docx_placeholders(tpl_path)
            logger.info("[DFD] Placeholders detectados (%d): %s", len(placeholders), placeholders)
        except Exception:
            pass
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
            # opcional: assunto final para histórico
            "assunto": assunto_final,
        }
        update_submission(sid, status="done", result=result, error=None)
        add_audit(
            KIND,
            "completed",
            actor,
            {
                "sid": sid,
                "filename": filename,
                "assunto": assunto_final,
                "objeto": ctx.get("objeto") or "",
            },
        )

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
        "assunto": (body.get("assunto") or "").strip(),
        "pcaAno": (body.get("pcaAno") or "").strip(),
        "diretoriaDemandante": none_if_empty(body.get("diretoriaDemandante")),
        "alinhamentoPE": (body.get("alinhamentoPE") or "").strip(),
        "justificativaNecessidade": (body.get("justificativaNecessidade") or "").strip(),
        "objeto": (body.get("objeto") or "").strip(),
        "prazosEnvolvidos": (body.get("prazosEnvolvidos") or "").strip(),
        "consequenciaNaoAquisicao": (body.get("consequenciaNaoAquisicao") or "").strip(),
        "grauPrioridade": none_if_empty(body.get("grauPrioridade")),
        "items": body.get("items") or [],
    }
    if not raw["modeloSlug"]:
        return err_json(422, code="validation_error", message="Timbre é obrigatório.")
    if not raw["numero"]:
        return err_json(422, code="validation_error", message="Número do memorando é obrigatório.")

    try:
        payload = DfdIn(**raw)
    except ValidationError as ve:
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
    request: Request,
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

        # AUDIT: download primário (formato inferido pela extensão)
        try:
            ext = (os.path.splitext(filename)[1] or "").lstrip(".").lower() or "auto"
            add_audit(KIND, "download", user, {
                "sid": sid,
                "filename": filename,
                "bytes": len(data),
                "fmt": ext,
                "ip": (getattr(request.client, "host", None) if request and request.client else None),
                "ua": (request.headers.get("user-agent") if request else None),
            })
        except Exception:
            logger.exception("audit (download legacy) failed (non-blocking)")

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
    request: Request,
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

        # AUDIT: download com formato explícito
        try:
            add_audit(KIND, "download", user, {
                "sid": sid,
                "filename": filename,
                "bytes": len(data),
                "fmt": fmt,
                "ip": (getattr(request.client, "host", None) if request and request.client else None),
                "ua": (request.headers.get("user-agent") if request else None),
            })
        except Exception:
            logger.exception("audit (download fmt) failed (non-blocking)")

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
