# apps/bff/app/automations/form2json.py
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from starlette.responses import JSONResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field, EmailStr, ConfigDict, ValidationError
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from uuid import uuid4
from io import BytesIO
import json
import logging

from app.db import insert_submission, update_submission, get_submission, list_submissions, add_audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/automations/form2json", tags=["automations:form2json"])

# ==============================================================================
# Helpers de erro/resposta
# ==============================================================================

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

def pydantic_errors(exc: Exception):
    """
    Converte erros do Pydantic em uma lista legível:
    [{"field": "itens.0.quantidade", "msg": "...", "type": "..."}]
    """
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

# ==============================================================================
# Models / Schema
# ==============================================================================

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

# ==============================================================================
# Auth helpers
# ==============================================================================

def _require_user(req: Request) -> Dict[str, Any]:
    user = req.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="não autenticado")
    return user

# ==============================================================================
# Payload builder
# ==============================================================================

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

# ==============================================================================
# Endpoints
# ==============================================================================

@router.get("/schema")
async def get_schema():
    try:
        return {"kind": KIND, "schema": SCHEMA}
    except Exception as e:
        logger.exception("schema error")
        return err_json(500, code="schema_error", message="Falha ao montar schema.", details=str(e))

@router.get("/submissions")
async def list_my_submissions(request: Request, limit: int = 50, offset: int = 0):
    try:
        actor = _require_user(request)
    except HTTPException as he:
        return err_json(he.status_code, code="unauthorized", message=str(he.detail))

    try:
        rows = list_submissions(kind=KIND, actor_cpf=actor.get("cpf"), limit=limit, offset=offset)
        return {"items": rows, "limit": limit, "offset": offset}
    except Exception as e:
        logger.exception("list_submissions error")
        return err_json(
            500, code="storage_error", message="Falha ao listar suas submissões.", details=str(e)
        )

@router.get("/submissions/{sid}")
async def get_submission_status(sid: str, request: Request):
    try:
        actor = _require_user(request)
    except HTTPException as he:
        return err_json(he.status_code, code="unauthorized", message=str(he.detail))

    try:
        row = get_submission(sid)
    except Exception as e:
        logger.exception("get_submission storage error")
        return err_json(500, code="storage_error", message="Falha ao consultar submissão.", details=str(e))

    if not row:
        return err_json(404, code="not_found", message="Submissão não encontrada.", details={"sid": sid})

    if row.get("actor_cpf") != actor.get("cpf"):
        return err_json(403, code="forbidden", message="Você não tem acesso a esta submissão.")

    return row

def _process_submission(sid: str, body: Form2JsonIn, actor: Dict[str, Any]):
    try:
        update_submission(sid, status="running")
    except Exception as e:
        logger.exception("update_submission to running failed")
        # se nem atualizar status, ainda tentamos auditar e marcar erro
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
async def submit(request: Request, background: BackgroundTasks):
    # Auth
    try:
        actor = _require_user(request)
    except HTTPException as he:
        return err_json(he.status_code, code="unauthorized", message=str(he.detail))

    # 1) Lê JSON cru
    try:
        raw = await request.json()
        if not isinstance(raw, dict):
            return err_json(
                400,
                code="invalid_json",
                message="O corpo da requisição deve ser um objeto JSON.",
                hint="Envie application/json com um objeto (chave/valor).",
            )
    except Exception as e:
        return err_json(
            400,
            code="invalid_json",
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
            400,
            code="invalid_field",
            message="O campo 'itens' deve ser uma lista.",
            received={"type": type(itens).__name__},
            hint="Envie 'itens' como array de objetos { descricao, quantidade }.",
        )

    for idx, it in enumerate(itens):
        if not isinstance(it, dict):
            # ignora silenciosamente ou acusa? aqui optamos por apontar erro
            return err_json(
                400,
                code="invalid_item",
                message=f"Item em 'itens[{idx}]' deve ser um objeto.",
                received={"value_type": type(it).__name__},
            )
        desc = (it.get("descricao") or "").strip()
        q = safe_int(it.get("quantidade", 0), default=0)
        norm_itens.append({"descricao": desc, "quantidade": q})
    raw["itens"] = norm_itens

    # 3) Validação Pydantic
    try:
        body = Form2JsonIn.model_validate(raw)
    except Exception as e:
        return err_json(
            400,
            code="invalid_payload",
            message="O corpo enviado não passou na validação.",
            details=pydantic_errors(e),
            received=raw,
        )

    # 4) Persistência
    sid = str(uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    try:
        insert_submission({
            "id": sid, "kind": KIND, "version": FORM2JSON_VERSION,
            "actor_cpf": actor.get("cpf"), "actor_nome": actor.get("nome"), "actor_email": actor.get("email"),
            "payload": json.dumps(raw, ensure_ascii=False),
            "status": "queued", "result": None, "error": None,
            "created_at": now, "updated_at": now
        })
        add_audit(KIND, "submitted", actor, {"sid": sid})
    except Exception as e:
        logger.exception("insert_submission error")
        return err_json(
            500,
            code="storage_error",
            message="Falha ao salvar a submissão.",
            details=str(e),
        )

    # 5) Processamento assíncrono
    background.add_task(_process_submission, sid, body, actor)
    return {"submissionId": sid, "status": "queued"}

@router.post("/submissions/{sid}/download")
async def download_result(sid: str, request: Request):
    # Auth
    try:
        actor = _require_user(request)
    except HTTPException as he:
        return err_json(he.status_code, code="unauthorized", message=str(he.detail))

    # Busca
    try:
        row = get_submission(sid)
    except Exception as e:
        logger.exception("get_submission storage error (download)")
        return err_json(500, code="storage_error", message="Falha ao consultar submissão.", details=str(e))

    if not row:
        return err_json(404, code="not_found", message="Submissão não encontrada.", details={"sid": sid})

    if row.get("actor_cpf") != actor.get("cpf"):
        return err_json(403, code="forbidden", message="Você não tem acesso a esta submissão.")

    status = row.get("status")
    if status != "done":
        return err_json(
            409,
            code="not_ready",
            message="Resultado ainda não está disponível para download.",
            details={"status": status},
            hint="Aguarde o status 'done' e tente novamente.",
        )

    # Download
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

@router.get("/ui")
async def form2json_ui():
    # serve UI simples (sem try/except; se falhar, 500 padrão)
    html = """<!doctype html>
<html lang="pt-BR">
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Formulário para JSON (BFF)</title>
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu; background:#f6f7f9; margin:0; padding:24px;}
  .wrap{max-width:960px; margin:0 auto;}
  .card{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:16px;}
  .row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  label{display:grid;gap:6px;margin:8px 0}
  input,select{padding:8px 10px;border:1px solid #cbd5e1;border-radius:8px}
  button{padding:8px 12px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;cursor:pointer}
  .primary{background:#0369a1;color:#fff;border-color:#0369a1}
  pre{background:#f1f5f9;padding:12px;border-radius:10px;overflow:auto;max-height:50vh}
  .tag{font-size:11px;border:1px solid #e5e7eb;border-radius:999px;padding:2px 8px;background:#f8fafc;color:#334155}
  .items{display:grid;gap:8px;margin:6px 0}
  .item{display:grid;grid-template-columns:5fr 1fr auto;gap:8px}
  pre{
    background:#f1f5f9;
    padding:12px;
    border-radius:10px;
    overflow:auto;
    max-height:50vh;
    white-space:pre-wrap;     /* quebra linhas longas */
    word-break:break-word;
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    font-size:13px;
    line-height:1.5;
  }
</style>
<div class="wrap">
  <h1>Formulário para JSON <span class="tag">BFF + iframe</span></h1>
  <p>Esta UI é servida pelo BFF e consome os endpoints da automação.</p>
  <div class="row" style="margin-top:12px">
    <div class="card">
      <label>Nome <input id="f_nome"/></label>
      <label>Email <input id="f_email" type="email"/></label>
      <div class="row">
        <label>Departamento <input id="f_dep" value="AGEPAR"/></label>
        <label>Prioridade
          <select id="f_prio">
            <option value="baixa">Baixa</option><option value="media">Média</option><option value="alta">Alta</option>
          </select>
        </label>
      </div>
      <label>Data <input id="f_data" type="date"/></label>
      <label style="display:flex;align-items:center;gap:8px">
        <input id="f_termos" type="checkbox"/> Aceito os termos
      </label>

      <div>
        <div style="font-size:14px;color:#475569;margin-top:8px">Itens</div>
        <div id="items" class="items"></div>
        <button onclick="addItem()">+ Adicionar item</button>
      </div>

      <div style="margin-top:12px;display:flex;gap:8px">
        <button class="primary" onclick="submitForm()" id="btnSubmit">Enviar</button>
        <button onclick="downloadJSON()" id="btnDown" disabled>Baixar .json</button>
      </div>

      <div id="status" style="margin-top:8px;color:#334155;font-size:14px"></div>
    </div>

    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div style="font-weight:600">Resultado</div>
        <button onclick="copyOut()">Copiar</button>
      </div>
      <pre id="out">Envie e aguarde...</pre>
    </div>
  </div>
</div>
<script>
let sid = null;

function pretty(v){
  try{
    // se já for objeto, ok; se for string JSON, parseia e reserializa
    const obj = typeof v === "string" ? JSON.parse(v) : v;
    return JSON.stringify(obj, null, 2);
  }catch{
    // se não for JSON válido, mostra cru mesmo
    return String(v ?? "");
  }
}

function el(id){ return document.getElementById(id); }
function addItem(data={descricao:"", quantidade:1}){
  const box = el("items");
  const row = document.createElement("div");
  row.className="item";
  row.innerHTML = `
    <input placeholder="Descrição" value="${data.descricao||""}"/>
    <input type="number" min="0" value="${data.quantidade||1}"/>
    <button onclick="this.parentElement.remove()">Remover</button>
  `;
  box.appendChild(row);
}
addItem();

function payload(){
  const itemsBox = el("items").children;
  const itens = [];
  for (const r of itemsBox){
    const [d,q] = r.querySelectorAll("input");
    if (d.value.trim()){
      itens.push({descricao:d.value.trim(), quantidade:Number(q.value)||0});
    }
  }
  return {
    nome: el("f_nome").value||null,
    email: el("f_email").value||null,
    departamento: el("f_dep").value||null,
    prioridade: el("f_prio").value,
    data: el("f_data").value||null,
    aceitaTermos: el("f_termos").checked,
    itens
  };
}

async function submitForm(){
  el("status").textContent = "enviando...";
  el("btnSubmit").disabled = true;
  el("btnDown").disabled = true;
  try{
    const r = await fetch("/api/automations/form2json/submit", {
      method:"POST",
      credentials:"include",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify(payload())
    });
    if(!r.ok){
      let msgObj = { status: r.status, statusText: r.statusText };
      try{ msgObj = await r.json(); }catch{}
      el("status").textContent = "erro de validação";
      el("out").textContent = pretty(msgObj);   // <- aqui
      el("btnSubmit").disabled = false;
      return;
    }
    const {submissionId} = await r.json();
    sid = submissionId;
    el("status").textContent = "queued • SID="+sid;
    poll();
  }catch(e){
    el("status").textContent = "erro: "+e.message;
    el("btnSubmit").disabled = false;
  }
}

async function poll(){
  if(!sid) return;
  try{
    const r = await fetch(`/api/automations/form2json/submissions/${sid}`, {credentials:"include"});
    if(!r.ok) throw new Error("status "+r.status);
    const s = await r.json();
    el("status").textContent = "status: "+s.status;
    if(s.status==="done"){
      el("out").textContent = pretty(s.result); // <- aqui (antes era s.result direto)
      el("btnSubmit").disabled = false;
      el("btnDown").disabled = false;
      return;
    }
    if(s.status==="error"){
      el("out").textContent = pretty(s.error || s); // mostra erro legível
      el("btnSubmit").disabled = false;
      return;
    }

    setTimeout(poll, 900);
  }catch(e){
    el("status").textContent = "erro: "+e.message;
    el("btnSubmit").disabled = false;
  }
}

async function downloadJSON(){
  if(!sid) return;
  const r = await fetch(`/api/automations/form2json/submissions/${sid}/download`, {
    method:"POST", credentials:"include"
  });
  if(!r.ok){
    let msg = `download ${r.status}`;
    try{ msg = JSON.stringify(await r.json(), null, 2); }catch{}
    alert(msg);
    return;
  }
  const blob = await r.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "form2json.json";
  document.body.appendChild(a); a.click(); a.remove();
}

async function copyOut(){
  try{ await navigator.clipboard.writeText(el("out").textContent || ""); }catch{}
}
</script>
"""
    return HTMLResponse(html)
