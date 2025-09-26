from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Depends
from starlette.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field, ConfigDict, ValidationError, model_validator
from typing import Optional, Dict, Any, List
from datetime import datetime, date
from zoneinfo import ZoneInfo
from uuid import uuid4
from io import BytesIO
import json
import logging
import os
import pathlib
import mimetypes
import re
import zipfile
import subprocess
import shutil

from app.db import (
    insert_submission,
    update_submission,
    get_submission,
    list_submissions,
    add_audit,
    list_audits,
)
from app.auth.rbac import require_roles_any  # RBAC

# =============== PDF FILL (inline util para reduzir dependências externas) ===============
# Observação: este util usa 'pdfrw'. Adicione `pdfrw` ao requirements se ainda não existir.
try:
    from pdfrw import PdfReader, PdfWriter, PdfDict, PdfName
except Exception:  # pragma: no cover
    PdfReader = PdfWriter = PdfDict = PdfName = None  # type: ignore


def _flatten_pdf(in_path: str, out_path: str) -> None:
    """
    Achata (flatten) o PDF preenchido para garantir que os valores apareçam em qualquer viewer.
    Tenta qpdf; se falhar, tenta Ghostscript. Se ambos falharem, lança RuntimeError.
    """
    try:
        subprocess.run(
            ["qpdf", "--replace-input", "--object-streams=generate", in_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if in_path != out_path:
            shutil.copyfile(in_path, out_path)
        return
    except Exception:
        pass

    try:
        subprocess.run(
            [
                "gs", "-dBATCH", "-dNOPAUSE", "-dSAFER",
                "-sDEVICE=pdfwrite", "-dPrinted",
                f"-sOutputFile={out_path}", in_path
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return
    except Exception as e:
        raise RuntimeError("Não foi possível achatar o PDF (qpdf/gs indisponível).") from e


def _pdf_fill_acroform(template_path: str, out_path: str, fields: Dict[str, str]) -> None:
    """
    Preenche um PDF AcroForm e garante 'appearance streams' consistentes:
      - Define DA/DR (fonte Helvetica, cor preta)
      - Seta NeedAppearances=true
      - Remove AP de cada anotação preenchida (forçando regeneração)
      - Opcionalmente 'flatten' via qpdf/gs se FERIAS_FLATTEN=1
    """
    if PdfReader is None:
        raise RuntimeError("Dependência 'pdfrw' não disponível no ambiente do BFF.")
    if not os.path.exists(template_path):
        raise FileNotFoundError(template_path)

    pdf = PdfReader(template_path)

    # --- Garante DA/DR no AcroForm (appearance default) ---
    helv = PdfDict(
        Type=PdfName.Font,
        Subtype=PdfName.Type1,
        BaseFont=PdfName.Helvetica,
        Name=PdfName.Helv,
    )
    acro = getattr(pdf.Root, "AcroForm", None) or PdfDict()
    acro.update(PdfDict(
        NeedAppearances=PdfName("true"),
        DA=" /Helv 0 Tf 0 g",
        DR=PdfDict(Font=PdfDict(Helv=helv))
    ))
    pdf.Root.AcroForm = acro

    # --- Preenche os campos ---
    for page in pdf.pages:
        ann = getattr(page, "Annots", None)
        if not ann:
            continue
        for a in ann:
            name = a.get("/T")
            if not name:
                continue
            key = name.to_unicode() if hasattr(name, "to_unicode") else str(name).strip("()")
            if key in fields:
                val = fields.get(key) or ""
                a.update(PdfDict(V=f"{val}", AS=f"{val}"))
                try:
                    if a.get("/AP"):
                        del a["/AP"]
                except Exception:
                    pass

    PdfWriter().write(out_path, pdf)

    if os.getenv("FERIAS_FLATTEN", "0").lower() in ("1", "true", "yes"):
        try:
            _flatten_pdf(out_path, out_path)
        except Exception as e:
            logging.getLogger(__name__).warning("Falha ao achatar PDF: %s", e)


def _mark_exclusive(options: Dict[str, str], pick: str) -> Dict[str, str]:
    """Marca 'X' somente na opção 'pick'; limpa as demais."""
    out: Dict[str, str] = {}
    for alias, field_name in options.items():
        out[field_name] = "X" if alias == pick else ""
    return out

# =========================================================================================

logger = logging.getLogger(__name__)

KIND = "ferias"
FERIAS_VERSION = "0.2.2"
REQUIRED_ROLES = ("ferias",)
ELEVATED_ROLES = ("admin", "coordenador")

FERIAS_DEBUG_LOG = os.getenv("FERIAS_DEBUG_LOG", "0").lower() in ("1", "true", "yes")

TPL_DIR = pathlib.Path(__file__).resolve().parent / "templates" / "ferias"

def _resolve_pdf_dir() -> pathlib.Path:
    env_dir = os.environ.get("FERIAS_PDF_DIR")
    if env_dir:
        p = pathlib.Path(env_dir).resolve()
        if p.exists():
            logger.info("[FERIAS] Usando FERIAS_PDF_DIR=%s", p)
            return p
        logger.warning("[FERIAS] FERIAS_PDF_DIR informado mas inexistente: %s", p)

    here = pathlib.Path(__file__).resolve()
    candidates = [
        here.parents[1] / "templates" / "pdf",
        here.parents[2] / "templates" / "pdf",
        here.parents[2] / "apps" / "bff" / "templates" / "pdf",
        pathlib.Path("/app/templates/pdf"),
        pathlib.Path.cwd() / "templates" / "pdf",
    ]
    for c in candidates:
        if c.exists():
            logger.info("[FERIAS] PDF_TPL_DIR resolvido para %s", c)
            return c

    logger.error("[FERIAS] Nenhum diretório de PDF encontrado nos candidatos: %s", candidates)
    return candidates[0]

PDF_TPL_DIR = _resolve_pdf_dir()
REQ_PDF = PDF_TPL_DIR / "requerimento_de_ferias.pdf"
SUB_PDF = PDF_TPL_DIR / "substituicao_de_ferias.pdf"


# ---------------------- Helpers ----------------------
def err_json(status: int, **payload):
    return StreamingResponse(
        BytesIO(json.dumps(payload, ensure_ascii=False).encode("utf-8")),
        status_code=status,
        media_type="application/json; charset=utf-8",
    )


def _to_obj(x, default=None):
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


def _has_any_role(user: Dict[str, Any], *roles: str) -> bool:
    user_roles = set((user or {}).get("roles") or [])
    return any(r in user_roles for r in roles)


def _owns_submission(row: Dict[str, Any], user: Dict[str, Any]) -> bool:
    u_cpf = (user.get("cpf") or "").strip() or None
    u_email = (user.get("email") or "").strip() or None
    owner_cpf = (row.get("actor_cpf") or "").strip() or None
    owner_email = (row.get("actor_email") or "").strip() or None
    return bool(
        (owner_cpf and u_cpf and owner_cpf == u_cpf) or
        (not owner_cpf and owner_email and u_email and owner_email == u_email)
    )


def _can_access_submission(row: Dict[str, Any], user: Dict[str, Any]) -> bool:
    if _owns_submission(row, user):
        return True
    if _has_any_role(user, *ELEVATED_ROLES):
        return True
    return False


def _read_html(name: str) -> str:
    path = TPL_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# ---------------------- Models & Validation ----------------------
DATE_RX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_date_iso(d: str) -> date:
    if not d or not DATE_RX.match(d.strip()):
        raise ValueError("Data inválida; use 'YYYY-MM-DD'.")
    y, m, dd = map(int, d.split("-"))
    return date(y, m, dd)


def _days_inclusive(a: date, b: date) -> int:
    return (b - a).days + 1


class Substituto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    nome: str = Field(..., min_length=1)


class Periodo(BaseModel):
    inicio: str
    fim: str


class FeriasIn(BaseModel):
    """
    Modelo da UI nova: um requerimento com 1..3 períodos.
    Campos:
      - protocolo: string (obrigatório)
      - periodos: [{inicio, fim}] (1..3)
      - exercicio: int (ano)
      - tipo: 'terco' | 'saldo'
      - observacoes: string (linhas "Nome: X | RG: Y | ...")
      - substituto: { nome } | null
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    protocolo: str = Field(..., min_length=3)
    periodos: List[Periodo] = Field(..., min_length=1, max_length=3)
    exercicio: int = Field(..., ge=1990, le=2100)
    tipo: str = Field("terco")
    observacoes: Optional[str] = ""
    substituto: Optional[Substituto] = None

    @model_validator(mode="after")
    def _validate_periods(self):
        lead = 30 if (self.tipo or "terco") == "terco" else 10
        today_sp = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        min_start_ordinal = today_sp.toordinal() + lead
        for i, p in enumerate(self.periodos):
            ini = _parse_date_iso(p.inicio)
            fim = _parse_date_iso(p.fim)
            dias = _days_inclusive(ini, fim)
            if dias < 10:
                raise ValueError(f"Período #{i+1}: deve ter ao menos 10 dias (contagem inclusiva).")
            if ini.toordinal() < min_start_ordinal:
                raise ValueError(f"Período #{i+1}: início deve ser ≥ hoje + {lead} dias.")
        return self


# Schema apenas informativo
SCHEMA = {
    "title": "Férias — Requerimento + Substituição (UI custom, multi-períodos)",
    "version": FERIAS_VERSION,
    "fields": [
        {"name": "protocolo", "type": "text", "label": "Protocolo"},
        {"name": "periodos[].inicio", "type": "date", "label": "Início do período"},
        {"name": "periodos[].fim", "type": "date", "label": "Fim do período"},
        {"name": "exercicio", "type": "number", "label": "Exercício"},
        {"name": "tipo", "type": "select", "label": "Tipo de férias"},
        {"name": "observacoes", "type": "textarea", "label": "Observações"},
        {"name": "substituto.nome", "type": "text", "label": "Substituto (opcional)"},
    ],
}

# ==== FIELD MAPS ====
# Ajuste as strings abaixo para os nomes REAIS dos campos do seu PDF.
REQ_FIELD_MAP = {
    "nome": "Caixa de texto 1_3",
    "rg": "Caixa de texto 1_4",
    "cargo": "Caixa de texto 1_5",
    "lf": "Caixa de texto 1",
    "nivel": "Caixa de texto 1_6",
    "lotacao": "Caixa de texto 1_2",
    "exercicio": "Caixa de texto 2",
    "data_inicio": ["Caixa de texto 3_4", "Caixa de texto 3", "Caixa de texto 3_7"],
    "data_termino": ["Caixa de texto 3_5", "Caixa de texto 3_2", "Caixa de texto 3_8"],
    "dias": ["Caixa de texto 3_6", "Caixa de texto 3_3", "Caixa de texto 3_9"],
    "local": "Caixa de texto 1_7",
    "data": "Caixa de texto 1_8",
    "servidor": "Caixa de texto 1_9",
    # Novo campo - ajuste para o nome do seu AcroForm:
    "protocolo": "Protocolo",  # ex.: "Protocolo" ou "Caixa de texto 1_10"
}

SUB_FIELD_MAP = {
    "favoravel": "Caixa de texto 3",
    "nao_favoravel": "Caixa de texto 3_2",
    "sim": "Caixa de texto 3_3",
    "nao": "Caixa de texto 3_4",
    "substituto": "Caixa de texto 1",
    "periodo": "Caixa de texto 1_5",
    "local": "Caixa de texto 1_2",
    "data": "Caixa de texto 1_3",
    "chefia_imediata": "Caixa de texto 1_4",
    # Novo campo - ajuste para o nome do seu AcroForm:
    "protocolo": "Protocolo",  # ex.: "Protocolo" ou outro nome
}

# ---------------------- Router ----------------------
router = APIRouter(prefix=f"/api/automations/{KIND}", tags=[f"automation:{KIND}"])


@router.get("/schema")
async def get_schema():
    return {"kind": KIND, "schema": SCHEMA}


@router.get("/submissions")
async def list_my_submissions(
    request: Request,
    user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES)),
    limit: int = 50,
    offset: int = 0,
):
    cpf = (user.get("cpf") or "").strip() or None
    email = (user.get("email") or "").strip() or None
    if not cpf and not email:
        return err_json(422, code="identity_missing", message="Sem CPF/e-mail para filtrar submissões. Faça login novamente.")
    try:
        rows = list_submissions(kind=KIND, actor_cpf=cpf, actor_email=None if cpf else email, limit=limit, offset=offset)
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


def _format_br(iso_date: str) -> str:
    try:
        y, m, d = iso_date.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso_date


_OBS_KEY_RX = re.compile(r"\s*([^:]+):\s*(.+?)\s*$")


def _parse_observacoes(obs: Optional[str]) -> Dict[str, str]:
    """Converte a string 'A: 1 | B: 2 | ...' (gerada pela UI) em dict{"a":"1","b":"2"}."""
    out: Dict[str, str] = {}
    if not obs:
        return out
    parts = [p.strip() for p in (obs or "").split("|")]
    for p in parts:
        m = _OBS_KEY_RX.match(p)
        if not m:
            continue
        k = (m.group(1) or "").strip().lower()
        v = (m.group(2) or "").strip()
        out[k] = v
    return out


def _process_submission(sid: str, body: FeriasIn, actor: Dict[str, Any]) -> None:
    """Gera 2 PDFs (requerimento + substituicao) a partir do payload multi-períodos."""
    try:
        update_submission(sid, status="running", error=None)
        add_audit(KIND, "running", actor, {"sid": sid, "protocolo": body.protocolo})
    except Exception as e:
        logger.exception("update to running failed")
        try:
            update_submission(sid, status="error", error=f"storage: {e}")
        except Exception:
            pass
        try:
            add_audit(KIND, "failed", actor, {"sid": sid, "error": f"storage: {e}", "protocolo": getattr(body, "protocolo", None)})
        except Exception:
            pass
        return

    try:
        # Verifica existência dos templates ANTES de tentar preencher
        missing = []
        for p in (REQ_PDF, SUB_PDF):
            if not p.exists():
                missing.append(str(p))
        if missing:
            msg = f"Templates PDF não encontrados: {', '.join(missing)} (defina FERIAS_PDF_DIR corretamente)."
            logger.error("[FERIAS] %s", msg)
            raise FileNotFoundError(msg)

        raw = body.model_dump()
        obs_map = _parse_observacoes(raw.get("observacoes"))
        # Campos esperados no obs: Nome, RG, Cargo, LF, Nível, Lotação, Exercício, Tipo, Despacho, Necessidade de substituição, Substituto, Período substituto, Chefia imediata
        ident_nome = obs_map.get("nome", "")
        ident_rg = obs_map.get("rg", "")
        ident_cargo = obs_map.get("cargo", "")
        ident_lf = obs_map.get("lf", "")
        ident_nivel = obs_map.get("nível", obs_map.get("nivel", ""))
        ident_lotacao = obs_map.get("lotação", obs_map.get("lotacao", ""))
        chefia_imediata = obs_map.get("chefia imediata", "")
        despacho_txt = obs_map.get("despacho", "")
        necessidade_txt = obs_map.get("necessidade de substituição", "")
        substituto_nome = (raw.get("substituto") or {}).get("nome") or obs_map.get("substituto", "")
        periodo_subst_txt = obs_map.get("período substituto", obs_map.get("periodo substituto", ""))
        protocolo = raw.get("protocolo") or ""

        # Caminho de saída
        out_dir = f"/app/data/files/{KIND}/{sid}"
        os.makedirs(out_dir, exist_ok=True)

        # Períodos (1..3)
        periods: List[Dict[str, str]] = []
        for p in (raw.get("periodos") or []):
            ini_iso = _parse_date_iso(p["inicio"]).isoformat()
            fim_iso = _parse_date_iso(p["fim"]).isoformat()
            periods.append({"inicio": ini_iso, "fim": fim_iso})

        # dias_total (apenas metadado; também vamos preencher por linha)
        dias_total = 0
        for p in periods:
            dias_total += _days_inclusive(_parse_date_iso(p["inicio"]), _parse_date_iso(p["fim"]))

        # data do dia (base São Paulo)
        today_iso = datetime.now(ZoneInfo("America/Sao_Paulo")).date().isoformat()
        today_br = _format_br(today_iso)

        # ---------- Preenche Requerimento ----------
        req_fields: Dict[str, str] = {
            REQ_FIELD_MAP["nome"]: ident_nome,
            REQ_FIELD_MAP["rg"]: ident_rg,
            REQ_FIELD_MAP["cargo"]: ident_cargo,
            REQ_FIELD_MAP["lf"]: ident_lf,
            REQ_FIELD_MAP["nivel"]: ident_nivel,
            REQ_FIELD_MAP["lotacao"]: ident_lotacao,
            REQ_FIELD_MAP["exercicio"]: str(raw.get("exercicio") or ""),
            REQ_FIELD_MAP["local"]: "Curitiba / PR",
            REQ_FIELD_MAP["data"]: today_br,
            REQ_FIELD_MAP["servidor"]: ident_nome,
        }
        # Protocolo (se mapeado)
        if "protocolo" in REQ_FIELD_MAP and REQ_FIELD_MAP["protocolo"]:
            req_fields[REQ_FIELD_MAP["protocolo"]] = protocolo

        # Preenche as 3 linhas conforme a quantidade de períodos, INCLUINDO o campo de DIAS
        for i in range(3):
            if i < len(periods):
                ini_br = _format_br(periods[i]["inicio"])
                fim_br = _format_br(periods[i]["fim"])
                dias_i = _days_inclusive(_parse_date_iso(periods[i]["inicio"]), _parse_date_iso(periods[i]["fim"]))
                req_fields[REQ_FIELD_MAP["data_inicio"][i]]  = ini_br
                req_fields[REQ_FIELD_MAP["data_termino"][i]] = fim_br
                req_fields[REQ_FIELD_MAP["dias"][i]]         = str(dias_i)
            else:
                req_fields[REQ_FIELD_MAP["data_inicio"][i]]  = ""
                req_fields[REQ_FIELD_MAP["data_termino"][i]] = ""
                req_fields[REQ_FIELD_MAP["dias"][i]]         = ""

        req_out = os.path.join(out_dir, "requerimento.pdf")
        _pdf_fill_acroform(str(REQ_PDF), req_out, req_fields)

        # ---------- Preenche Substituição ----------
        txt = (despacho_txt or "").strip().lower()
        fav_pick = "favoravel" if txt.startswith("favor") else ("nao_favoravel" if txt else "favoravel")
        nec = (necessidade_txt or "").strip().lower()
        nec_pick = "sim" if nec.startswith("sim") else ("nao" if nec else "sim")

        sub_fields: Dict[str, str] = {}
        sub_fields.update(_mark_exclusive(
            {"favoravel": SUB_FIELD_MAP["favoravel"], "nao_favoravel": SUB_FIELD_MAP["nao_favoravel"]},
            fav_pick
        ))
        sub_fields.update(_mark_exclusive(
            {"sim": SUB_FIELD_MAP["sim"], "nao": SUB_FIELD_MAP["nao"]},
            nec_pick
        ))

        if periodo_subst_txt:
            periodo_txt = periodo_subst_txt
        else:
            periodo_txt = "; ".join([f"{_format_br(p['inicio'])} a {_format_br(p['fim'])}" for p in periods])

        sub_fields[SUB_FIELD_MAP["substituto"]] = substituto_nome
        sub_fields[SUB_FIELD_MAP["periodo"]] = periodo_txt
        sub_fields[SUB_FIELD_MAP["local"]] = "Curitiba / PR"
        sub_fields[SUB_FIELD_MAP["data"]] = today_br
        sub_fields[SUB_FIELD_MAP["chefia_imediata"]] = chefia_imediata
        # Protocolo (se mapeado)
        if "protocolo" in SUB_FIELD_MAP and SUB_FIELD_MAP["protocolo"]:
            sub_fields[SUB_FIELD_MAP["protocolo"]] = protocolo

        sub_out = os.path.join(out_dir, "substituicao.pdf")
        _pdf_fill_acroform(str(SUB_PDF), sub_out, sub_fields)

        manifest = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "engine": f"{KIND}@{FERIAS_VERSION}",
            "protocolo": protocolo,
            "periodos": periods,
            "dias_total": dias_total,
            "exercicio": raw.get("exercicio"),
            "arquivos": [
                {"kind": "requerimento", "file_path": req_out, "filename": f"requerimento_{sid}.pdf"},
                {"kind": "substituicao", "file_path": sub_out, "filename": f"substituicao_{sid}.pdf"},
            ],
        }
        update_submission(sid, status="done", result=manifest, error=None)
        add_audit(KIND, "completed", actor, {"sid": sid, "protocolo": protocolo})

    except Exception as e:
        logger.exception("processing error")
        try:
            update_submission(sid, status="error", error=str(e))
        except Exception:
            pass
        try:
            add_audit(KIND, "failed", actor, {"sid": sid, "error": str(e), "protocolo": getattr(body, "protocolo", None)})
        except Exception:
            pass


@router.post("/submit")
async def submit_ferias(
    request: Request,
    body: Dict[str, Any],
    background: BackgroundTasks,
    user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES)),
):
    # Retrocompat: se vier inicio/fim isolados, converte para periodos=[{...}]
    periodos = body.get("periodos")
    if not periodos:
        ini = (body.get("inicio") or "").strip()
        fim = (body.get("fim") or "").strip()
        if ini or fim:
            periodos = [{"inicio": ini, "fim": fim}]
    raw = {
        "protocolo": (body.get("protocolo") or "").strip(),
        "periodos": periodos or [],
        "exercicio": body.get("exercicio"),
        "tipo": (body.get("tipo") or "terco").strip(),
        "observacoes": (body.get("observacoes") or "").strip(),
        "substituto": body.get("substituto") or None,
    }

    if FERIAS_DEBUG_LOG:
        try:
            logger.info("[FERIAS][SUBMIT] raw_payload=%s", json.dumps(raw, ensure_ascii=False))
        except Exception:
            logger.exception("[FERIAS][SUBMIT] failed to log raw payload")

    try:
        payload = FeriasIn(**raw)
    except ValidationError as ve:
        try:
            logger.warning(
                "[FERIAS][SUBMIT][422] validation_error errors=%s raw=%s",
                ve.errors(), json.dumps(raw, ensure_ascii=False)
            )
        except Exception:
            logger.exception("[FERIAS][SUBMIT][422] failed to log validation_error")
        return err_json(422, code="validation_error", message="Erro de validação nos campos.", details=ve.errors())
    except Exception as ve:
        logger.exception("validation error on submit")
        return err_json(422, code="validation_error", message="Erro de validação.", details=str(ve))

    if FERIAS_DEBUG_LOG:
        try:
            lead = 30 if (payload.tipo or "terco") == "terco" else 10
            today_sp = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
            logger.info("[FERIAS][SUBMIT] validated periodos=%s tipo=%s protocolo=%s today_sp=%s lead=%s",
                        json.dumps(payload.model_dump().get("periodos")),
                        (payload.tipo or "terco"),
                        payload.protocolo,
                        today_sp.isoformat(), lead)
        except Exception:
            logger.exception("[FERIAS][SUBMIT] failed to log validated summary")

    sid = str(uuid4())
    sub = {
        "id": sid,
        "kind": KIND,
        "version": FERIAS_VERSION,
        "actor_cpf": user.get("cpf"),
        "actor_nome": user.get("nome"),
        "actor_email": user.get("email"),
        "payload": payload.model_dump(exclude_none=True),
        "status": "queued",
        "result": None,
        "error": None,
    }
    try:
        insert_submission(sub)
        add_audit(KIND, "submitted", user, {"sid": sid, "protocolo": payload.protocolo})
    except Exception as e:
        logger.exception("insert_submission failed")
        return err_json(500, code="storage_error", message="Falha ao salvar a submissão.", details=str(e))

    logger.info("[FERIAS] Submissão %s criada por %s (%s) proto=%s", sid, user.get("nome"), user.get("cpf"), payload.protocolo)
    background.add_task(_process_submission, sid, payload, user)
    return {"submissionId": sid, "status": "queued", "protocolo": payload.protocolo}


# -------- DOWNLOADS --------
@router.post("/submissions/{sid}/download")
async def download_zip(
    sid: str,
    request: Request,
    user: Dict[str, Any] = Depends(require_roles_any("ferias", "coordenador", "admin")),
):
    """Baixa um ZIP contendo os dois PDFs gerados."""
    try:
        row = get_submission(sid)
    except Exception as e:
        logger.exception("get_submission (download) failed")
        return err_json(500, code="storage_error", message="Falha ao consultar submissão.", details=str(e))

    if not row:
        return err_json(404, code="not_found", message="Submissão não encontrada.", details={"sid": sid})
    if not _can_access_submission(row, user):
        return err_json(403, code="forbidden", message="Você não tem acesso a esta submissão.")
    if row.get("status") != "done":
        return err_json(409, code="not_ready", message="Resultado ainda não está pronto.", details={"status": row.get("status")})

    result = _to_obj(row.get("result"), {})
    files = result.get("arquivos") or []
    if not files:
        return err_json(410, code="file_not_found", message="Arquivos não disponíveis.")

    mem = BytesIO()
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in files:
            fp = item.get("file_path")
            fn = item.get("filename") or os.path.basename(fp or "")
            if fp and os.path.exists(fp):
                zf.write(fp, arcname=fn)
    mem.seek(0)

    try:
        add_audit(KIND, "download", user, {"sid": sid, "fmt": "zip", "protocolo": result.get("protocolo")})
    except Exception:
        logger.exception("audit (download) failed (non-blocking)")

    return StreamingResponse(
        mem,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="ferias_{sid}.zip"'},
    )


@router.post("/submissions/{sid}/download/{fmt}")
async def download_one(
    sid: str,
    fmt: str,
    request: Request,
    user: Dict[str, Any] = Depends(require_roles_any("ferias", "coordenador", "admin")),
):
    """Baixa especificamente 'requerimento' ou 'substituicao'."""
    if fmt not in ("requerimento", "substituicao"):
        return err_json(400, code="bad_request", message="Formato inválido. Use 'requerimento' ou 'substituicao'.")

    try:
        row = get_submission(sid)
    except Exception as e:
        logger.exception("get_submission (download fmt) failed")
        return err_json(500, code="storage_error", message="Falha ao consultar submissão.", details=str(e))

    if not row:
        return err_json(404, code="not_found", message="Submissão não encontrada.", details={"sid": sid})
    if not _can_access_submission(row, user):
        return err_json(403, code="forbidden", message="Você não tem acesso a esta submissão.")
    if row.get("status") != "done":
        return err_json(409, code="not_ready", message="Resultado ainda não está pronto.", details={"status": row.get("status")})

    result = _to_obj(row.get("result"), {})
    files = result.get("arquivos") or []
    pick = next((x for x in files if x.get("kind") == fmt), None)
    if not pick:
        return err_json(410, code="file_not_found", message="Arquivo não disponível.", details={"fmt": fmt})

    file_path = pick.get("file_path")
    filename = pick.get("filename") or f"{fmt}_{sid}.pdf"
    if not file_path or not os.path.exists(file_path):
        return err_json(410, code="file_not_found", message="Arquivo não está mais disponível.", details={"sid": sid, "fmt": fmt})

    with open(file_path, "rb") as f:
        data = f.read()

    try:
        add_audit(KIND, "download", user, {"sid": sid, "fmt": fmt, "bytes": len(data), "protocolo": result.get("protocolo")})
    except Exception:
        logger.exception("audit (download fmt) failed (non-blocking)")

    media_type = mimetypes.guess_type(filename)[0] or "application/pdf"
    return StreamingResponse(
        BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
@router.get("/ui/")
async def ferias_ui(request: Request):
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
async def ferias_history_ui(request: Request):
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

    try:
        html = _read_html("history.html")
    except FileNotFoundError:
        html = """<!doctype html><meta charset='utf-8'/><title>Férias — Histórico</title>
        <div style='font-family:system-ui;padding:24px'>
          <h1>Histórico — Férias</h1>
          <p>Use <code>GET /api/automations/ferias/submissions</code> e os downloads desta automação.</p>
        </div>"""
    return HTMLResponse(html)
