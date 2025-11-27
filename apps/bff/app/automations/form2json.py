# apps/bff/app/automations/form2json.py
"""
Automação "form2json": recebe um formulário JSON, valida e persiste uma submissão,
gera um JSON normalizado como resultado e oferece consultas e download.

Segurança/RBAC
--------------
- As rotas de JSON exigem o papel configurado em `REQUIRED_ROLES`, via `require_roles_any`.
- A rota de UI realiza checagem manual para retornar HTML amigável em 401/403.

Efeitos colaterais
------------------
- Persistência e leitura via `app.db` (`insert_submission`, `update_submission`,
  `get_submission`, `list_submissions`, `add_audit`).
- Registro de auditoria para eventos de submissão, execução, conclusão e falhas.

Variáveis/Constantes
--------------------
- KIND: identificador lógico da automação ("form2json").
- FORM2JSON_VERSION: versão do "engine" para rastreabilidade.
- SCHEMA: descrição informativa dos campos esperados pela UI/cliente.
"""

from __future__ import annotations

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
from app.auth.rbac import require_roles_any

logger = logging.getLogger(__name__)

REQUIRED_ROLES = ("automations.form2json",)

router = APIRouter(
    prefix="/api/automations/form2json",
    tags=["automations:form2json"],
)


def err_json(
    status: int,
    *,
    code: str,
    message: str,
    details: Any = None,
    hint: Optional[str] = None,
    received: Any = None,
) -> JSONResponse:
    """
    Constrói uma resposta JSON padronizada de erro.

    Parâmetros
    ----------
    status : int
        Código HTTP a ser retornado.
    code : str
        Código curto do erro.
    message : str
        Mensagem principal do erro.
    details : Any, opcional
        Estrutura com detalhes adicionais.
    hint : Optional[str], opcional
        Sugestão de correção para o cliente.
    received : Any, opcional
        Payload recebido (para diagnóstico).

    Retorna
    -------
    JSONResponse
        Resposta JSON com o envelope de erro.
    """
    content: Dict[str, Any] = {"error": code, "message": message}
    if details is not None:
        content["details"] = details
    if hint is not None:
        content["hint"] = hint
    if received is not None:
        content["received"] = received
    return JSONResponse(status_code=status, content=content)


def pydantic_errors(exc: Exception) -> List[Dict[str, Any]]:
    """
    Converte erros do Pydantic em uma lista enxuta de mensagens por campo.

    Parâmetros
    ----------
    exc : Exception
        Exceção capturada.

    Retorna
    -------
    List[Dict[str, Any]]
        Lista contendo objetos com 'field', 'msg' e 'type'.
    """
    if isinstance(exc, ValidationError):
        out = []
        for e in exc.errors():
            loc = ".".join(str(p) for p in e.get("loc", []))
            out.append({"field": loc, "msg": e.get("msg"), "type": e.get("type")})
        return out
    return [{"field": "", "msg": str(exc)}]


def safe_int(value: Any, default: int = 0) -> int:
    """
    Converte valor para inteiro com fallback.

    Parâmetros
    ----------
    value : Any
        Valor de entrada.
    default : int
        Valor de retorno quando a conversão falhar.

    Retorna
    -------
    int
        Valor inteiro convertido ou 'default'.
    """
    try:
        return int(value)
    except Exception:
        return default


class FormItem(BaseModel):
    """
    Item do formulário, com descrição e quantidade.

    Atributos
    ---------
    descricao : str
        Descrição do item (máx. 500 chars).
    quantidade : int
        Quantidade não negativa.
    """
    descricao: str = Field("", max_length=500)
    quantidade: int = Field(1, ge=0)


class Form2JsonIn(BaseModel):
    """
    Modelo de entrada do formulário.

    Atributos
    ---------
    nome : Optional[str]
    email : Optional[EmailStr]
    departamento : Optional[str]
    prioridade : Literal['baixa','media','alta']
        Prioridade do pedido (default: 'baixa').
    data : Optional[str]
        Data em formato YYYY-MM-DD (não validada aqui).
    aceita_termos : bool
        Aceite dos termos (alias: 'aceitaTermos').
    itens : List[FormItem]
        Lista de itens do pedido.

    Observações
    -----------
    - Campos extras são ignorados (ConfigDict extra='ignore').
    """
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
        {"name": "prioridade", "type": "select", "label": "Prioridade", "options": ["baixa", "media", "alta"], "default": "baixa"},
        {"name": "data", "type": "date", "label": "Data"},
        {"name": "aceitaTermos", "type": "checkbox", "label": "Aceito os termos"},
        {"name": "itens", "type": "array", "label": "Itens", "itemShape": {"descricao": "", "quantidade": 1}},
    ],
}


def _build_payload(body: Form2JsonIn, actor: Dict[str, Any]) -> Dict[str, Any]:
    """
    Constrói o JSON final normalizado a partir do modelo validado.

    Parâmetros
    ----------
    body : Form2JsonIn
        Dados validados do formulário.
    actor : Dict[str, Any]
        Usuário autenticado (cpf, nome, email).

    Retorna
    -------
    Dict[str, Any]
        Payload final que será retornado como resultado da submissão.
    """
    return {
        "nome": (body.nome or None),
        "email": (body.email or None),
        "departamento": (body.departamento or None),
        "prioridade": body.prioridade,
        "data": (body.data or None),
        "aceitaTermos": bool(body.aceita_termos),
        "itens": [
            {"descricao": i.descricao.strip(), "quantidade": int(i.quantidade or 0)}
            for i in body.itens
            if (i.descricao or "").strip()
        ],
        "metadata": {
            "engine": f"{KIND}@{FORM2JSON_VERSION}",
            "geradoEm": datetime.utcnow().isoformat() + "Z",
            "actor": {
                "cpf": actor.get("cpf"),
                "nome": actor.get("nome"),
                "email": actor.get("email"),
            },
        },
    }


@router.get("/schema")
async def get_schema() -> Dict[str, Any]:
    """
    Retorna o schema informativo para clientes/UI.

    Retorna
    -------
    Dict[str, Any]
        Dicionário com 'kind' e 'schema'.

    Exceções
    --------
    500 Internal Server Error
        Em caso de erro inesperado na construção do schema.
    """
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
) -> Dict[str, Any]:
    """
    Lista submissões do usuário autenticado.

    Parâmetros
    ----------
    request : Request
        Requisição atual (não usada diretamente além de contexto).
    user : Dict[str, Any]
        Usuário autenticado (obtido via RBAC).
    limit : int
        Limite de registros.
    offset : int
        Deslocamento.

    Retorna
    -------
    Dict[str, Any]
        {'items': [...], 'limit': int, 'offset': int}

    Exceções
    --------
    500 Internal Server Error
        Falha ao consultar o armazenamento.
    """
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
    """
    Obtém o status e dados de uma submissão do próprio usuário.

    Parâmetros
    ----------
    sid : str
        ID da submissão.
    user : Dict[str, Any]
        Usuário autenticado (RBAC).

    Retorna
    -------
    Dict[str, Any]
        Registro completo da submissão.

    Exceções
    --------
    404 Not Found
        Submissão inexistente.
    403 Forbidden
        Submissão não pertence ao usuário.
    500 Internal Server Error
        Falha no acesso ao armazenamento.
    """
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


def _process_submission(sid: str, body: Form2JsonIn, actor: Dict[str, Any]) -> None:
    """
    Processa uma submissão: atualiza status, gera o JSON final e audita.

    Parâmetros
    ----------
    sid : str
        Identificador da submissão.
    body : Form2JsonIn
        Dados validados do formulário.
    actor : Dict[str, Any]
        Usuário autenticado (cpf, nome, email).

    Efeitos colaterais
    ------------------
    - Atualiza a submissão no armazenamento (status/result).
    - Emite eventos de auditoria ('completed' ou 'failed').
    """
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
    """
    Recebe o formulário JSON bruto, normaliza, valida, persiste a submissão
    e agenda o processamento assíncrono.

    Parâmetros
    ----------
    request : Request
        Usada para obter o corpo JSON.
    background : BackgroundTasks
        Agendador para processamento offline.
    user : Dict[str, Any]
        Usuário autenticado (RBAC).

    Retorna
    -------
    Dict[str, Any]
        {'submissionId': str, 'status': 'queued'}

    Exceções
    --------
    400 Bad Request
        JSON inválido, tipo de campo incorreto ou payload inválido.
    500 Internal Server Error
        Falha ao salvar a submissão.
    """
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

    def none_if_empty(v: Any) -> Any:
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

    sid = str(uuid4())
    now = datetime.utcnow().isoformat() + "Z"
    try:
        insert_submission(
            {
                "id": sid,
                "kind": KIND,
                "version": FORM2JSON_VERSION,
                "actor_cpf": user.get("cpf"),
                "actor_nome": user.get("nome"),
                "actor_email": user.get("email"),
                "payload": json.dumps(raw, ensure_ascii=False),
                "status": "queued",
                "result": None,
                "error": None,
                "created_at": now,
                "updated_at": now,
            }
        )
        add_audit(KIND, "submitted", user, {"sid": sid})
    except Exception as e:
        logger.exception("insert_submission error")
        return err_json(500, code="storage_error", message="Falha ao salvar a submissão.", details=str(e))

    background.add_task(_process_submission, sid, body, user)
    return {"submissionId": sid, "status": "queued"}


@router.post("/submissions/{sid}/download")
async def download_result(
    sid: str,
    user: Dict[str, Any] = Depends(require_roles_any(*REQUIRED_ROLES)),
):
    """
    Realiza o download do JSON resultante da submissão do próprio usuário.

    Parâmetros
    ----------
    sid : str
        ID da submissão.
    user : Dict[str, Any]
        Usuário autenticado (RBAC).

    Retorna
    -------
    StreamingResponse
        Fluxo JSON com `application/json; charset=utf-8`.

    Exceções
    --------
    404 Not Found
        Submissão inexistente.
    403 Forbidden
        Submissão não pertence ao usuário.
    409 Conflict
        Resultado ainda não está pronto.
    500 Internal Server Error
        Falha ao preparar o arquivo para download.
    """
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
        return err_json(
            409,
            code="not_ready",
            message="Resultado ainda não está disponível para download.",
            details={"status": status},
            hint="Aguarde o status 'done' e tente novamente.",
        )

    data = row.get("result") or "{}"
    try:
        buf = BytesIO(data.encode("utf-8"))
    except Exception as e:
        logger.exception("encode error on download")
        return err_json(
            500,
            code="encoding_error",
            message="Falha ao preparar o arquivo para download.",
            details=str(e),
        )

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
async def form2json_ui(request: Request):
    """
    UI HTML (iframe) com verificação manual de acesso.

    Comportamento
    -------------
    - Em caso de 401/403, retorna página HTML simples com a mensagem apropriada.
    - Caso autorizado, retorna HTML básico (placeholder) da automação.

    Parâmetros
    ----------
    request : Request
        Requisição atual.

    Retorna
    -------
    HTMLResponse
        Página HTML.

    Observações de segurança
    ------------------------
    Esta rota não usa `Depends` explicitamente para RBAC para que possamos
    customizar a resposta HTML nos casos 401/403.
    """
    checker = require_roles_any(*REQUIRED_ROLES)
    try:
        checker(request)
    except HTTPException as he:
        status = he.status_code
        msg = (
            "Faça login para acessar esta automação."
            if status == 401
            else "Você não tem permissão para acessar esta automação."
        )
        html_err = f"""<!doctype html><meta charset="utf-8"/><title>Acesso</title>
        <div style="font-family:system-ui;padding:24px">
          <h1 style="margin:0 0 8px">{status}</h1>
          <p style="color:#334155">{msg}</p>
        </div>"""
        return HTMLResponse(html_err, status_code=status)

    html = """<!doctype html>
    <meta charset="utf-8"/>
    <title>Form2JSON</title>
    <div style="font-family:system-ui;padding:24px">
      <h1>Form2JSON</h1>
      <p>Use a API desta automação para enviar formulários e baixar o JSON gerado.</p>
    </div>"""
    return HTMLResponse(html)
