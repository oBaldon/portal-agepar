
---

# PROMPT DE ARRANQUE — Nova Automação BFF + iframe (Portal AGEPAR)

## Contexto & Objetivo

Você é engenheiro(a) full-stack sênior. Crie uma **automação modular** no padrão do Portal AGEPAR, com:

* **Backend (BFF / FastAPI)** : um *router* isolado em `app/automations/{kind}.py`, responsável por schema, submissão, polling de status, download e UI (HTML) embutida via iframe.
* **Frontend (Host/React)** :  **sem código novo** . O host é  *catalog-driven* ; basta publicar/atualizar um bloco no `catalog.dev.json` apontando o iframe para a automação do BFF.
* **Persistência** : use a camada `app.db` já existente (`insert_submission`, `update_submission`, `get_submission`, `list_submissions`, `add_audit`) para submissões e trilha de auditoria.
* **Autenticação** : **mock** via sessão (cookie), com `_require_user()` garantindo usuário autenticado.
* **DX** : sobe em dev via Docker Compose já existente.

> Troque `{KIND}` pelo identificador curto da automação (ex.: `form2json`, `cadastrar_protocolo`), `{TITLE}` pelo nome visível (ex.: “Cadastro de Protocolo”), `{VERSION}` (ex.: `1.0.0`).

---

## Entregáveis (arquivos e alterações)

1. **Router da automação**

* **Caminho** : `apps/bff/app/automations/{KIND}.py`
* **Conteúdo base (copie e ajuste):**

```python
# apps/bff/app/automations/{KIND}.py
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from starlette.responses import JSONResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from uuid import uuid4
from io import BytesIO
import json

from app.db import insert_submission, update_submission, get_submission, list_submissions, add_audit

router = APIRouter(prefix=f"/api/automations/{'{KIND}'}", tags=[f"automations:{'{KIND}'}"])

# ==== Models / Schema (exemplo) ====
class Item(BaseModel):
    descricao: str = Field("", max_length=500)
    quantidade: int = Field(1, ge=0)

class InPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    # campos de exemplo / ajuste como quiser:
    nome: Optional[str] = None
    email: Optional[EmailStr] = None
    prioridade: Literal["baixa", "media", "alta"] = "baixa"
    data: Optional[str] = None
    aceita_termos: bool = Field(False, alias="aceitaTermos")
    itens: List[Item] = Field(default_factory=list)

KIND = "{KIND}"
TITLE = "{TITLE}"
VERSION = "{VERSION}"

SCHEMA = {
    "title": TITLE,
    "version": VERSION,
    "fields": [
        {"name": "nome", "type": "text", "label": "Nome"},
        {"name": "email", "type": "email", "label": "Email"},
        {"name": "prioridade", "type": "select", "label": "Prioridade", "options": ["baixa","media","alta"], "default": "baixa"},
        {"name": "data", "type": "date", "label": "Data"},
        {"name": "aceitaTermos", "type": "checkbox", "label": "Aceito os termos"},
        {"name": "itens", "type": "array", "label": "Itens", "itemShape": {"descricao":"", "quantidade":1}},
    ]
}

def _require_user(req: Request) -> Dict[str, Any]:
    user = req.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="não autenticado")
    return user

def _build_output(body: InPayload, actor: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "nome": body.nome or None,
        "email": body.email or None,
        "prioridade": body.prioridade,
        "data": body.data or None,
        "aceitaTermos": bool(body.aceita_termos),
        "itens": [
            {"descricao": i.descricao.strip(), "quantidade": int(i.quantidade or 0)}
            for i in body.itens if (i.descricao or "").strip()
        ],
        "metadata": {
            "engine": f"{KIND}@{VERSION}",
            "geradoEm": datetime.utcnow().isoformat() + "Z",
            "actor": {"cpf": actor.get("cpf"), "nome": actor.get("nome"), "email": actor.get("email")},
        },
    }

# ==== Endpoints ====
@router.get("/schema")
async def get_schema():
    return {"kind": KIND, "schema": SCHEMA}

@router.get("/submissions")
async def list_my_submissions(request: Request, limit: int = 50, offset: int = 0):
    actor = _require_user(request)
    rows = list_submissions(kind=KIND, actor_cpf=actor.get("cpf"), limit=limit, offset=offset)
    return {"items": rows, "limit": limit, "offset": offset}

@router.get("/submissions/{sid}")
async def get_submission_status(sid: str, request: Request):
    actor = _require_user(request)
    row = get_submission(sid)
    if not row:
      raise HTTPException(status_code=404, detail="not found")
    if row.get("actor_cpf") != actor.get("cpf"):
      raise HTTPException(status_code=403, detail="forbidden")
    # Se quiser, normalize result p/ objeto:
    try:
        if row.get("result") and isinstance(row["result"], str):
            json.loads(row["result"])
    except Exception:
        pass
    return row

def _process_submission(sid: str, body: InPayload, actor: Dict[str, Any]):
    try:
        update_submission(sid, status="running")
        result = _build_output(body, actor)
        update_submission(sid, status="done", result=json.dumps(result, ensure_ascii=False), error=None)
        add_audit(KIND, "completed", actor, {"sid": sid})
    except Exception as e:
        update_submission(sid, status="error", error=str(e))
        add_audit(KIND, "failed", actor, {"sid": sid, "error": str(e)})

@router.post("/submit")
async def submit(request: Request, background: BackgroundTasks):
    actor = _require_user(request)

    # 1) JSON bruto
    try:
        raw = await request.json()
        if not isinstance(raw, dict):
            raise ValueError("payload precisa ser objeto JSON")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"json inválido: {e}")

    # 2) Normalizações
    def none_if_empty(v): return None if isinstance(v, str) and v.strip()=="" else v
    raw["nome"] = none_if_empty(raw.get("nome"))
    raw["email"] = none_if_empty(raw.get("email"))
    raw["data"] = none_if_empty(raw.get("data"))
    if "aceitaTermos" in raw and "aceita_termos" not in raw:
        raw["aceita_termos"] = bool(raw.get("aceitaTermos"))

    norm_itens = []
    for it in (raw.get("itens") or []):
        if not isinstance(it, dict): continue
        desc = (it.get("descricao") or "").strip()
        q = it.get("quantidade", 0)
        try: q = int(q)
        except: q = 0
        if desc: norm_itens.append({"descricao": desc, "quantidade": q})
    raw["itens"] = norm_itens

    # 3) Validação Pydantic (erro legível)
    try:
        body = InPayload.model_validate(raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"payload inválido: {e}")

    # 4) Persistência (submissão)
    sid = str(uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    insert_submission({
        "id": sid, "kind": KIND, "version": VERSION,
        "actor_cpf": actor.get("cpf"), "actor_nome": actor.get("nome"), "actor_email": actor.get("email"),
        "payload": json.dumps(raw, ensure_ascii=False),
        "status": "queued", "result": None, "error": None,
        "created_at": now, "updated_at": now
    })
    add_audit(KIND, "submitted", actor, {"sid": sid})

    # 5) Processamento
    background.add_task(_process_submission, sid, body, actor)
    return {"submissionId": sid, "status": "queued"}

@router.post("/submissions/{sid}/download")
async def download_result(sid: str, request: Request):
    actor = _require_user(request)
    row = get_submission(sid)
    if not row: raise HTTPException(status_code=404, detail="not found")
    if row.get("actor_cpf") != actor.get("cpf"):
        raise HTTPException(status_code=403, detail="forbidden")
    if row.get("status") != "done":
        raise HTTPException(status_code=409, detail=f"status={row.get('status')}")
    data = row.get("result") or "{}"
    buf = BytesIO(data.encode("utf-8"))
    filename = f"{KIND}_{datetime.utcnow().date().isoformat()}.json"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(buf, media_type="application/json; charset=utf-8", headers=headers)

@router.get("/ui")
async def ui():
    html = f"""<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{TITLE} (BFF)</title>
<style>
  body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu; background:#f6f7f9; margin:0; padding:24px}}
  .wrap{{max-width:960px; margin:0 auto}}
  .card{{background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:16px}}
  .row{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
  label{{display:grid;gap:6px;margin:8px 0}}
  input,select{{padding:8px 10px;border:1px solid #cbd5e1;border-radius:8px}}
  button{{padding:8px 12px;border:1px solid #cbd5e1;border-radius:8px;background:#fff;cursor:pointer}}
  .primary{{background:#0369a1;color:#fff;border-color:#0369a1}}
  pre{{background:#f1f5f9;padding:12px;border-radius:10px;overflow:auto;max-height:50vh;white-space:pre-wrap;word-break:break-word;font-family:ui-monospace,Consolas,Monaco,monospace;font-size:13px;line-height:1.5}}
  .tag{{font-size:11px;border:1px solid #e5e7eb;border-radius:999px;padding:2px 8px;background:#f8fafc;color:#334155}}
  .items{{display:grid;gap:8px;margin:6px 0}}
  .item{{display:grid;grid-template-columns:5fr 1fr auto;gap:8px}}
</style>
<div class="wrap">
  <h1>{TITLE} <span class="tag">{KIND}@{VERSION} • BFF + iframe</span></h1>
  <p>UI servida pelo BFF; consome os endpoints desta automação.</p>
  <div class="row" style="margin-top:12px">
    <div class="card">
      <label>Nome <input id="f_nome"/></label>
      <label>Email <input id="f_email" type="email"/></label>
      <label>Prioridade
        <select id="f_prio"><option value="baixa">Baixa</option><option value="media">Média</option><option value="alta">Alta</option></select>
      </label>
      <label>Data <input id="f_data" type="date"/></label>
      <label style="display:flex;align-items:center;gap:8px"><input id="f_termos" type="checkbox"/> Aceito os termos</label>
      <div><div style="font-size:14px;color:#475569;margin-top:8px">Itens</div><div id="items" class="items"></div><button onclick="addItem()">+ Adicionar item</button></div>
      <div style="margin-top:12px;display:flex;gap:8px">
        <button class="primary" onclick="submitForm()" id="btnSubmit">Enviar</button>
        <button onclick="downloadJSON()" id="btnDown" disabled>Baixar .json</button>
      </div>
      <div id="status" style="margin-top:8px;color:#334155;font-size:14px"></div>
    </div>
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center"><div style="font-weight:600">Resultado</div><button onclick="copyOut()">Copiar</button></div>
      <pre id="out">Envie e aguarde...</pre>
    </div>
  </div>
</div>
<script>
let sid = null;
function el(id){{ return document.getElementById(id); }}
function addItem(data={{descricao:"", quantidade:1}}){{ const box=el("items"); const row=document.createElement("div"); row.className="item"; row.innerHTML=`<input placeholder="Descrição" value="${{data.descricao||""}}"/><input type="number" min="0" value="${{data.quantidade||1}}"/><button onclick="this.parentElement.remove()">Remover</button>`; box.appendChild(row); }}
addItem();
function payload(){{ const itens=[]; for(const r of el("items").children){{ const [d,q]=r.querySelectorAll("input"); if(d.value.trim()) itens.push({{descricao:d.value.trim(), quantidade:Number(q.value)||0}}); }} return {{nome:el("f_nome").value||null,email:el("f_email").value||null,prioridade:el("f_prio").value,data:el("f_data").value||null,aceitaTermos:el("f_termos").checked,itens}}; }}
function pretty(v){{ try{{ const o=typeof v==="string"?JSON.parse(v):v; return JSON.stringify(o,null,2); }}catch{{ return String(v??""); }} }}
async function submitForm(){{ el("status").textContent="enviando..."; el("btnSubmit").disabled=true; el("btnDown").disabled=true;
  try{{ const r=await fetch("{'/api/automations/'+KIND+'/submit'}".replace("KIND","{KIND}"),{{method:"POST",credentials:"include",headers:{{"Content-Type":"application/json"}},body:JSON.stringify(payload())}}); if(!r.ok){{ let msg={{status:r.status}}; try{{msg=await r.json();}}catch{{}} el("status").textContent="erro de validação"; el("out").textContent=pretty(msg); el("btnSubmit").disabled=false; return; }} const {{submissionId}}=await r.json(); sid=submissionId; el("status").textContent="queued • SID="+sid; poll(); }}
  catch(e){{ el("status").textContent="erro: "+e.message; el("btnSubmit").disabled=false; }} }}
async function poll(){{ if(!sid) return; try{{ const r=await fetch("{'/api/automations/'+KIND+'/submissions/'}".replace("KIND","{KIND}")+sid,{{credentials:"include"}}); if(!r.ok) throw new Error("status "+r.status); const s=await r.json(); el("status").textContent="status: "+s.status; if(s.status==="done"){{ el("out").textContent=pretty(s.result); el("btnSubmit").disabled=false; el("btnDown").disabled=false; return; }} if(s.status==="error"){{ el("out").textContent=pretty(s.error||s); el("btnSubmit").disabled=false; return; }} setTimeout(poll, 800); }}
  catch(e){{ el("status").textContent="erro: "+e.message; el("btnSubmit").disabled=false; }} }}
async function downloadJSON(){{ if(!sid) return; const r=await fetch("{'/api/automations/'+KIND+'/submissions/'}".replace("KIND","{KIND}")+sid+"/download",{{method:"POST",credentials:"include"}}); if(!r.ok){{ alert("download "+r.status); return; }} const blob=await r.blob(); const a=document.createElement("a"); a.href=URL.createObjectURL(blob); a.download="{KIND}.json"; document.body.appendChild(a); a.click(); a.remove(); }}
async function copyOut(){{ try{{ await navigator.clipboard.writeText(el("out").textContent||""); }}catch{{}} }}
</script>
"""
    return HTMLResponse(html)
```

2. **Registrar o router no BFF**

* **Arquivo** : `apps/bff/app/app/main.py`
* **Faça** :
* `from app.automations.{KIND} import router as {KIND}_router`
* `APP.include_router({KIND}_router)`

3. **Atualizar o catálogo**

* **Arquivo** : `catalog/catalog.dev.json` (servido por `/catalog/dev`)
* **Adicionar bloco** :

```json
{
  "name": "{KIND}",
  "displayName": "{TITLE}",
  "version": "{VERSION}",
  "ui": { "type": "iframe", "url": "http://localhost:8000/api/automations/{KIND}/ui" },
  "navigation": [{ "label": "{TITLE}", "path": "/{KIND}", "icon": "Workflow" }],
  "routes": [{ "path": "/{KIND}", "kind": "iframe" }]
}
```

4. **Compose / Reload**

* Reinicie o BFF para recarregar rotas e catálogo:

```bash
docker compose -f infra/docker-compose.dev.yml restart bff
```

* O host já está observando o catálogo via `VITE_CATALOG_URL`. Abra:
  * `http://localhost:5173/inicio` (cards/links)
  * `http://localhost:5173/{KIND}` (iframe da automação)

---

## Contratos e Padrões

* **Autorização básica** : submissões e consultas só visíveis para o  **mesmo CPF** ; ajuste para RBAC quando necessário.
* **Erros legíveis** :
* 401: `{"detail":"não autenticado"}`
* 400: `{"detail":"json inválido: ..."} | {"detail":"payload inválido: ..."}`
* 404/403/409 conforme regras de submissão/consulta/download
* **Validação tolerante** :
* `populate_by_name=True` (aceita camelCase `aceitaTermos`)
* `extra="ignore"` (ignora campos não previstos)
* Normalização de array de itens e inteiros

---

## Smoke Tests (curl)

> Faça login no host para gerar o cookie de sessão; ou use navegador no iframe.

```bash
# Schema
curl -s http://localhost:8000/api/automations/{KIND}/schema | jq

# Submeter (autenticado via cookie do navegador; em curl você precisará -b "<cookie>")
curl -s -X POST http://localhost:8000/api/automations/{KIND}/submit \
  -H "Content-Type: application/json" \
  -b 'portal_agepar_session=<COLAR COOKIE>' \
  -d '{"nome":"Teste","email":"t@e.com","prioridade":"media","data":"2025-09-01","aceitaTermos":true,"itens":[{"descricao":"X","quantidade":2}]}'

# Poll
curl -s -b 'portal_agepar_session=<COOKIE>' http://localhost:8000/api/automations/{KIND}/submissions/<SID> | jq

# Download
curl -s -X POST -b 'portal_agepar_session=<COOKIE>' \
  -D /dev/stdout \
  http://localhost:8000/api/automations/{KIND}/submissions/<SID>/download > out.json
```

---

## Checklist rápido

* [ ] Criei `app/automations/{KIND}.py` com endpoints: `/schema`, `/submit`, `/submissions`, `/submissions/{sid}`, `/submissions/{sid}/download`, `/ui`
* [ ] Importei & `include_router` na `main.py`
* [ ] Atualizei `catalog.dev.json` com o bloco `{KIND}`
* [ ] `docker compose -f infra/docker-compose.dev.yml restart bff`
* [ ] Abri `http://localhost:5173/{KIND}` e validei o fluxo (enviar, poll, baixar)

---

## Boas práticas para próximas automações

* **Versione** o `VERSION` dentro do módulo; grave-a em `result.metadata.engine`.
* **Observabilidade** : chame `add_audit` em marcos importantes (submitted, running, completed, failed).
* **Idempotência** (se necessário): dedupe por hash do payload antes de `insert_submission`.
* **Campos grandes** : se o result ficar muito grande, armazene em arquivo e sirva via link temporário.
* **Integrações externas** : encapsule chamadas em funções próprias e capture/exponha mensagens de falha legíveis.
