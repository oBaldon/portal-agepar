# apps/bff/app/automations/fileshare.py
"""
Automação de compartilhamento de arquivos (fileshare).

Propósito
---------
Permitir upload autenticado de arquivos, geração de links públicos assinados
com expiração, download autenticado (com ou sem proteção por senha), listagem
paginada de itens e limpeza de itens expirados.

Segurança/RBAC
--------------
- Router protegido por `require_roles_any("user", "coordenador", "admin")`.
- Todas as rotas exigem autenticação, exceto o download por token público.
- Download autenticado respeita proteção por senha, exceto para superusuário.
- Links públicos:
  - Itens protegidos: apenas o dono gera link e precisa informar a senha; superusuário pode gerar sem senha.
  - Itens não protegidos: qualquer usuário autenticado pode gerar.
- Exclusão: dono, admin ou superusuário.
- Limpeza imediata: admin ou superusuário.

Efeitos colaterais
------------------
- Persistência via `app.db` (create/get/list/inc_downloads/soft_delete/cleanup/audit).
- Escrita/leitura de arquivos em disco.
- Assinatura HMAC baseada em `SESSION_SECRET`.

Variáveis de ambiente
---------------------
- UPLOAD_ROOT: diretório raiz dos uploads (default: /data/uploads).
- SESSION_SECRET: segredo para assinar links.
- MAX_UPLOAD_SIZE: limite de bytes por upload (0 desabilita).
- UPLOAD_CHUNK_SIZE: tamanho do chunk em bytes (default: 1 MiB).
- ALLOWED_MIME_PREFIXES: lista CSV de prefixes MIME permitidos (ex.: "image/,application/pdf").
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    UploadFile,
    File,
    Form,
    BackgroundTasks,
)
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict

from app.auth.rbac import require_roles_any
from app import db as db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/automations/fileshare",
    tags=["automations", "fileshare"],
    dependencies=[Depends(require_roles_any("user", "coordenador", "admin"))],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

UPLOAD_ROOT = Path(os.getenv("UPLOAD_ROOT", "/data/uploads")).resolve()
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret").encode("utf-8")

TTL_MAP = {
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", "0"))
UPLOAD_CHUNK_SIZE = int(os.getenv("UPLOAD_CHUNK_SIZE", str(1024 * 1024)))
ALLOWED_MIME_PREFIXES = [
    p.strip() for p in os.getenv("ALLOWED_MIME_PREFIXES", "").split(",") if p.strip()
]


class ItemOut(BaseModel):
    """
    Representação pública de um item armazenado.

    Atributos
    ---------
    id : str
        Identificador do item.
    filename : str
        Nome original do arquivo.
    size : int
        Tamanho em bytes.
    content_type : Optional[str]
        MIME type informado no upload.
    owner_id : Optional[str]
        Identificador do dono (CPF).
    owner_name : Optional[str]
        Nome do dono no momento do upload.
    created_at : datetime
        Data/hora de criação (UTC).
    expires_at : datetime
        Data/hora de expiração (UTC).
    has_secret : bool
        Indica se o item é protegido por senha.
    downloads : int
        Contador de downloads.
    deleted_at : Optional[datetime]
        Timestamp de remoção lógica, se houver.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    id: str
    filename: str
    size: int
    content_type: Optional[str] = None
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    has_secret: bool = False
    downloads: int = 0
    deleted_at: Optional[datetime] = None


class Page(BaseModel):
    """
    Página de resultados paginados.

    Atributos
    ---------
    count : int
        Total de itens retornados.
    items : List[ItemOut]
        Lista de itens.
    """

    count: int
    items: List[ItemOut]


def _utcnow() -> datetime:
    """
    Retorna o timestamp atual em UTC.

    Retorna
    -------
    datetime
        Instante atual com tzinfo=UTC.
    """
    return datetime.now(timezone.utc)


def _sha256(s: str) -> str:
    """
    Calcula SHA-256 (hex) de uma string.

    Parâmetros
    ----------
    s : str
        Conteúdo base.

    Retorna
    -------
    str
        Hex digest.
    """
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _hash_secret(secret: str) -> str:
    """
    Gera hash de senha com salt.

    Parâmetros
    ----------
    secret : str
        Senha em texto claro.

    Retorna
    -------
    str
        Formato 'sha256:{salt}:{digest}'.
    """
    salt = secrets.token_hex(8)
    return f"sha256:{salt}:{_sha256(salt + secret)}"


def _check_secret(secret: str, secret_hash: str) -> bool:
    """
    Verifica uma senha contra o hash persistido.

    Parâmetros
    ----------
    secret : str
        Senha fornecida.
    secret_hash : str
        Hash no formato 'sha256:{salt}:{digest}'.

    Retorna
    -------
    bool
        True se válido; False caso contrário.
    """
    try:
        _algo, salt, digest = secret_hash.split(":", 2)
        return hmac.compare_digest(_sha256(salt + secret), digest)
    except Exception:
        return False


def _sign_link(data: str, exp: datetime) -> str:
    """
    Assina um token de link público com expiração.

    Parâmetros
    ----------
    data : str
        Dado a ser protegido (ex.: item_id).
    exp : datetime
        Expiração do link (UTC).

    Retorna
    -------
    str
        Token no formato '<data>.<exp_ts>.<sig_hex>'.
    """
    payload = f"{data}.{int(exp.timestamp())}"
    sig = hmac.new(SESSION_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify_link(token: str, now: Optional[datetime] = None) -> Optional[Dict[str, str]]:
    """
    Valida token assinado e janela de expiração.

    Parâmetros
    ----------
    token : str
        Token fornecido.
    now : Optional[datetime]
        Instante de referência; default = agora (UTC).

    Retorna
    -------
    Optional[Dict[str, str]]
        {'id': data, 'exp': exp_ts} se válido; None caso contrário.
    """
    now = now or _utcnow()
    try:
        data, exp_ts, sig = token.rsplit(".", 2)
        exp = datetime.fromtimestamp(int(exp_ts), tz=timezone.utc)
        if now > exp:
            return None
        expected = hmac.new(
            SESSION_SECRET, f"{data}.{exp_ts}".encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        return {"id": data, "exp": exp_ts}
    except Exception:
        return None


def _ensure_not_expired(row: Dict[str, Any]) -> None:
    """
    Garante que o item não foi apagado e não está expirado.

    Parâmetros
    ----------
    row : Dict[str, Any]
        Registro retornado do banco.

    Exceções
    --------
    HTTPException(404)
        Quando o item foi removido ou expirou.
    """
    if row.get("deleted_at"):
        raise HTTPException(status_code=404, detail="arquivo não encontrado")
    expires_at = row.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    if expires_at and _utcnow() > expires_at:
        raise HTTPException(status_code=404, detail="arquivo expirado")


def _owner_match(row: Dict[str, Any], user: Dict[str, Any]) -> bool:
    """
    Informa se o usuário é o dono do item.

    Parâmetros
    ----------
    row : Dict[str, Any]
        Registro do item.
    user : Dict[str, Any]
        Usuário autenticado.

    Retorna
    -------
    bool
        True se o CPF do usuário corresponde ao owner_id.
    """
    return (
        row.get("owner_id") and user and str(row.get("owner_id")) == str(user.get("cpf"))
    )


def _is_super(user: Optional[Dict[str, Any]]) -> bool:
    """
    Indica se o usuário possui flag de superusuário.

    Parâmetros
    ----------
    user : Optional[Dict[str, Any]]

    Retorna
    -------
    bool
        True quando superusuário.
    """
    return bool((user or {}).get("is_superuser"))


def _save_stream(dest: Path, up: UploadFile) -> int:
    """
    Salva o conteúdo enviado por upload em chunks para disco.

    Parâmetros
    ----------
    dest : Path
        Caminho destino do arquivo.
    up : UploadFile
        Arquivo recebido pelo FastAPI.

    Retorna
    -------
    int
        Tamanho escrito em bytes.

    Exceções
    --------
    HTTPException(413)
        Quando ultrapassa MAX_UPLOAD_SIZE.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    chunk_size = UPLOAD_CHUNK_SIZE if UPLOAD_CHUNK_SIZE > 0 else 1024 * 1024
    with dest.open("wb") as f:
        while True:
            chunk = up.file.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
            size += len(chunk)
            if MAX_UPLOAD_SIZE and size > MAX_UPLOAD_SIZE:
                try:
                    f.flush()
                finally:
                    pass
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413, detail="tamanho do arquivo excede o limite configurado"
                )
    return size


def _content_disposition_utf8(filename: str) -> Dict[str, str]:
    """
    Gera cabeçalho Content-Disposition compatível com UTF-8 (RFC 5987).

    Parâmetros
    ----------
    filename : str
        Nome do arquivo.

    Retorna
    -------
    Dict[str, str]
        Dicionário com a chave 'Content-Disposition'.
    """
    try:
        ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "download"
    except Exception:
        ascii_fallback = "download"
    fn_star = "UTF-8''" + quote(filename, safe="")
    return {
        "Content-Disposition": f'attachment; filename="{ascii_fallback}"; filename*={fn_star}'
    }


@router.get("/ui", response_class=HTMLResponse)
def get_ui(request: Request):
    """
    Renderiza a UI HTML do fileshare.

    Parâmetros
    ----------
    request : Request

    Retorna
    -------
    HTMLResponse
        Página HTML baseada em template.
    """
    return templates.TemplateResponse("fileshare/ui.html", {"request": request})


@router.get("/schema")
def get_schema():
    """
    Retorna o mini-esquema informativo da API.

    Retorna
    -------
    dict
        Descrição de rotas, campos e regras de autorização.
    """
    return {
        "POST /submit": {
            "fields": {"file": "binary", "ttl": "1d|7d|30d", "secret": "(opcional)"}
        },
        "GET /items": {"query": ["owner=(me|all)", "limit", "offset", "q"]},
        "GET /items/{id}": {"retorna": "metadados do item"},
        "POST /items/{id}/download": {
            "body": {"secret": "(opcional; exigido se protegido, exceto superuser)"}
        },
        "POST /items/{id}/share": {
            "body": {
                "expires": "1d|7d|30d",
                "secret": "(obrigatória se protegido, exceto superuser)",
            }
        },
        "POST /items/{id}/delete": {"owner ou admin/superuser"},
        "POST /tasks/cleanup": {"restrito": "admin/superuser"},
    }


@router.post("/submit", response_model=ItemOut)
async def upload(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    ttl: str = Form("7d"),
    secret: Optional[str] = Form(None),
):
    """
    Recebe upload autenticado, aplica política de MIME (opcional), persiste metadados
    e agenda limpeza assíncrona de expirados.

    Regras
    ------
    - Se ALLOWED_MIME_PREFIXES estiver definido, o MIME do upload deve iniciar por um dos prefixes.
    - Aplica TTL informado (1d, 7d, 30d); default=7d.
    - Senha opcional para proteção; armazenada com salt e SHA-256.

    Parâmetros
    ----------
    request : Request
        Usada para obter a sessão e o usuário.
    background : BackgroundTasks
        Agendador para tarefas de limpeza.
    file : UploadFile
        Arquivo enviado.
    ttl : str
        Tempo de vida do item: 1d|7d|30d.
    secret : Optional[str]
        Senha de proteção do item.

    Retorna
    -------
    ItemOut

    Exceções
    --------
    HTTPException(401)
        Não autenticado.
    HTTPException(415)
        Tipo MIME não permitido.
    HTTPException(413)
        Tamanho excede o limite configurado.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    if ALLOWED_MIME_PREFIXES:
        ct = (file.content_type or "").lower()
        if not any(ct.startswith(p.lower()) for p in ALLOWED_MIME_PREFIXES):
            raise HTTPException(
                status_code=415,
                detail="tipo de arquivo não permitido pela política do servidor",
            )

    if ttl not in TTL_MAP:
        raise HTTPException(status_code=422, detail="ttl inválido; use 1d, 7d ou 30d")

    exp = _utcnow() + TTL_MAP[ttl]

    item_id = secrets.token_urlsafe(10)
    daydir = _utcnow().strftime("%Y/%m/%d")
    dest = UPLOAD_ROOT / daydir / f"{item_id}"

    size = _save_stream(dest, file)
    secret_hash = _hash_secret(secret) if secret else None

    rec = {
        "id": item_id,
        "filename": file.filename,
        "size": size,
        "content_type": file.content_type,
        "path": str(dest),
        "owner_id": user.get("cpf"),
        "owner_name": user.get("nome"),
        "created_at": _utcnow().isoformat(),
        "expires_at": exp.isoformat(),
        "secret_hash": secret_hash,
        "downloads": 0,
        "deleted_at": None,
    }
    db.fileshare_create(rec)

    db.audit_log(
        actor=user,
        action="uploaded",
        kind="fileshare",
        target_id=item_id,
        meta={"filename": file.filename, "size": size, "ttl": ttl, "has_secret": bool(secret)},
    )

    background.add_task(db.fileshare_cleanup_expired, limit=200)

    return {
        "id": item_id,
        "filename": file.filename,
        "size": size,
        "content_type": file.content_type,
        "owner_id": rec["owner_id"],
        "owner_name": rec["owner_name"],
        "created_at": datetime.fromisoformat(rec["created_at"]),
        "expires_at": datetime.fromisoformat(rec["expires_at"]),
        "has_secret": bool(secret_hash),
        "downloads": 0,
        "deleted_at": None,
    }


@router.get("/items/{item_id}", response_model=ItemOut)
def get_item(item_id: str, request: Request):
    """
    Obtém metadados de um item específico.

    Parâmetros
    ----------
    item_id : str
        Identificador do item.
    request : Request
        Usada para autenticação.

    Retorna
    -------
    ItemOut

    Exceções
    --------
    HTTPException(401)
        Não autenticado.
    HTTPException(404)
        Arquivo inexistente, removido ou expirado.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    r = db.fileshare_get(item_id)
    if not r:
        raise HTTPException(status_code=404, detail="arquivo não encontrado")

    _ensure_not_expired(r)

    return {
        "id": r["id"],
        "filename": r["filename"],
        "size": r["size"],
        "content_type": r.get("content_type"),
        "owner_id": r.get("owner_id"),
        "owner_name": r.get("owner_name"),
        "created_at": r["created_at"],
        "expires_at": r["expires_at"],
        "has_secret": bool(r.get("secret_hash")),
        "downloads": r.get("downloads") or 0,
        "deleted_at": r.get("deleted_at"),
    }


@router.get("/items", response_model=Page)
def list_items(
    request: Request,
    owner: str = Query("all", pattern="^(all|me)$"),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """
    Lista itens com filtros e paginação.

    Parâmetros
    ----------
    request : Request
        Sessão autenticada.
    owner : str
        'all' ou 'me' para filtrar por dono.
    q : Optional[str]
        Termo de busca.
    limit : int
        Limite de itens.
    offset : int
        Deslocamento.

    Retorna
    -------
    Page

    Exceções
    --------
    HTTPException(401)
        Não autenticado.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    rows = db.fileshare_list(
        owner_id=user.get("cpf") if owner == "me" else None, q=q, limit=limit, offset=offset
    )

    items: List[Dict[str, Any]] = []
    for r in rows:
        try:
            _ensure_not_expired(r)
        except HTTPException:
            continue
        items.append(
            {
                "id": r["id"],
                "filename": r["filename"],
                "size": r["size"],
                "content_type": r.get("content_type"),
                "owner_id": r.get("owner_id"),
                "owner_name": r.get("owner_name"),
                "created_at": r["created_at"],
                "expires_at": r["expires_at"],
                "has_secret": bool(r.get("secret_hash")),
                "downloads": r.get("downloads") or 0,
                "deleted_at": r.get("deleted_at"),
            }
        )

    return {"count": len(items), "items": items}


@router.post("/items/{item_id}/download")
def download_item(item_id: str, request: Request, secret: Optional[str] = Form(None)):
    """
    Realiza download autenticado de um item.

    Regras
    ------
    - Se protegido por senha, exige 'secret' correto, exceto superusuário.
    - Incrementa contador de downloads e registra auditoria.

    Parâmetros
    ----------
    item_id : str
        Identificador do item.
    request : Request
        Sessão autenticada.
    secret : Optional[str]
        Senha, quando exigida.

    Retorna
    -------
    StreamingResponse
        Fluxo de bytes do arquivo.

    Exceções
    --------
    HTTPException(401)
        Não autenticado.
    HTTPException(403)
        Senha inválida ou ausente quando exigida.
    HTTPException(404)
        Item inexistente/indisponível/expirado.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    superuser = _is_super(user)

    r = db.fileshare_get(item_id)
    if not r:
        raise HTTPException(status_code=404, detail="arquivo não encontrado")

    _ensure_not_expired(r)

    secret_hash = r.get("secret_hash")
    if secret_hash and not superuser:
        if not secret or not _check_secret(secret, secret_hash):
            db.audit_log(
                actor=user,
                action="download_denied",
                kind="fileshare",
                target_id=item_id,
                meta={"reason": "secret_required"},
            )
            raise HTTPException(
                status_code=403, detail="chave secreta inválida ou ausente"
            )

    path = Path(r["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="arquivo indisponível")

    db.fileshare_inc_downloads(item_id)
    db.audit_log(
        actor=user,
        action="downloaded",
        kind="fileshare",
        target_id=item_id,
        meta={"filename": r["filename"], "superuser_override": superuser and bool(secret_hash)},
    )

    def _iterfile():
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    headers = _content_disposition_utf8(r["filename"])
    return StreamingResponse(
        _iterfile(),
        media_type=r.get("content_type") or "application/octet-stream",
        headers=headers,
    )


@router.post("/items/{item_id}/share")
def create_share_link(
    item_id: str,
    request: Request,
    expires: str = Form("7d"),
    secret: Optional[str] = Form(None),
):
    """
    Cria um link público assinado com expiração.

    Regras
    ------
    - Item protegido: apenas dono pode gerar, exigindo senha; superusuário pode gerar sem senha.
    - Item público: qualquer usuário autenticado pode gerar.

    Parâmetros
    ----------
    item_id : str
        Identificador do item.
    request : Request
        Sessão autenticada.
    expires : str
        TTL do link: 1d|7d|30d.
    secret : Optional[str]
        Senha quando item é protegido.

    Retorna
    -------
    dict
        {"download_url": "/api/automations/fileshare/share/<token>"}.

    Exceções
    --------
    HTTPException(401)
        Não autenticado.
    HTTPException(403)
        Não é dono de item protegido ou senha inválida.
    HTTPException(404)
        Arquivo não encontrado ou expirado.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    superuser = _is_super(user)

    r = db.fileshare_get(item_id)
    if not r:
        raise HTTPException(status_code=404, detail="arquivo não encontrado")

    _ensure_not_expired(r)

    protected = bool(r.get("secret_hash"))

    if protected:
        if not superuser:
            if not _owner_match(r, user):
                db.audit_log(
                    actor=user,
                    action="share_link_denied",
                    kind="fileshare",
                    target_id=item_id,
                    meta={"reason": "not_owner_protected"},
                )
                raise HTTPException(
                    status_code=403,
                    detail="apenas o dono pode gerar link para arquivo protegido",
                )
            if not secret or not _check_secret(secret, r["secret_hash"]):
                db.audit_log(
                    actor=user,
                    action="share_link_denied",
                    kind="fileshare",
                    target_id=item_id,
                    meta={"reason": "invalid_secret"},
                )
                raise HTTPException(status_code=403, detail="senha requerida para gerar link")

    if expires not in TTL_MAP:
        raise HTTPException(status_code=422, detail="expires inválido; use 1d, 7d ou 30d")

    exp = _utcnow() + TTL_MAP[expires]

    # Garante que o link nunca expira depois do próprio item.
    item_exp = r.get("expires_at")
    if isinstance(item_exp, str):
        try:
            item_exp = datetime.fromisoformat(item_exp.replace("Z", "+00:00"))
        except Exception:
            item_exp = None
    if isinstance(item_exp, datetime) and exp > item_exp:
        exp = item_exp
    token = _sign_link(r["id"], exp)

    db.audit_log(
        actor=user,
        action="shared_link_created",
        kind="fileshare",
        target_id=item_id,
        meta={"expires": exp.isoformat(), "public": not protected, "superuser_override": superuser and protected},
    )

    return {"download_url": f"/api/automations/fileshare/share/{token}"}


@router.get("/share/{token}")
def share_download(token: str):
    """
    Endpoint público para baixar via token assinado.

    Parâmetros
    ----------
    token : str
        Token assinado.

    Retorna
    -------
    StreamingResponse
        Conteúdo do arquivo.

    Exceções
    --------
    HTTPException(403)
        Token inválido ou expirado.
    HTTPException(404)
        Arquivo inexistente/expirado/indisponível.
    """
    data = _verify_link(token)
    if not data:
        raise HTTPException(status_code=403, detail="link inválido ou expirado")

    item_id = data["id"]
    r = db.fileshare_get(item_id)
    if not r:
        raise HTTPException(status_code=404, detail="arquivo não encontrado")

    _ensure_not_expired(r)

    path = Path(r["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="arquivo indisponível")

    db.fileshare_inc_downloads(item_id)
    db.audit_log(
        actor={"cpf": "anonymous"},
        action="downloaded_shared_link",
        kind="fileshare",
        target_id=item_id,
        meta={"via": "token"},
    )

    def _iterfile():
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    headers = _content_disposition_utf8(r["filename"])
    return StreamingResponse(
        _iterfile(),
        media_type=r.get("content_type") or "application/octet-stream",
        headers=headers,
    )


@router.post("/items/{item_id}/delete")
def delete_item(item_id: str, request: Request, background: BackgroundTasks):
    """
    Realiza remoção lógica do item e agenda remoção física do arquivo.

    Regras
    ------
    - Permitido ao dono, admin ou superusuário.

    Parâmetros
    ----------
    item_id : str
        Identificador do item.
    request : Request
        Sessão autenticada.
    background : BackgroundTasks
        Agendador para remoção física.

    Retorna
    -------
    dict
        {"ok": True}

    Exceções
    --------
    HTTPException(401)
        Não autenticado.
    HTTPException(403)
        Sem permissão.
    HTTPException(404)
        Item não encontrado.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    r = db.fileshare_get(item_id)
    if not r:
        raise HTTPException(status_code=404, detail="arquivo não encontrado")

    if not (_owner_match(r, user) or "admin" in (user.get("roles") or []) or _is_super(user)):
        raise HTTPException(status_code=403, detail="forbidden")

    db.fileshare_soft_delete(item_id)
    db.audit_log(
        actor=user, action="deleted", kind="fileshare", target_id=item_id, meta={"filename": r["filename"]}
    )

    p = Path(r["path"])
    if p.exists():
        background.add_task(lambda: p.unlink(missing_ok=True))

    return {"ok": True}


@router.post("/tasks/cleanup")
def cleanup_now(request: Request, limit: int = 200):
    """
    Executa limpeza imediata de itens expirados.

    Parâmetros
    ----------
    request : Request
        Sessão autenticada.
    limit : int
        Limite máximo de remoções nesta execução.

    Retorna
    -------
    dict
        {"expired_deleted": <int>}

    Exceções
    --------
    HTTPException(401)
        Não autenticado.
    HTTPException(403)
        Requer admin ou superusuário.
    """
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    if not (_is_super(user) or "admin" in (user.get("roles") or [])):
        raise HTTPException(status_code=403, detail="admin required")

    deleted = db.fileshare_cleanup_expired(limit=limit)
    return {"expired_deleted": deleted}