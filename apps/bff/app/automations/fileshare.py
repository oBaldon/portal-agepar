from __future__ import annotations
import hashlib, hmac, os, logging, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict

from app.auth.rbac import require_roles_any
from app import db as db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/automations/fileshare",
    tags=["automations", "fileshare"],
    dependencies=[Depends(require_roles_any("user","coordenador","admin"))],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# --- Config ---
UPLOAD_ROOT = Path(os.getenv("UPLOAD_ROOT", "/data/uploads")).resolve()
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret").encode("utf-8")

TTL_MAP = {
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}

# --- Models ---
class ItemOut(BaseModel):
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
    count: int
    items: List[ItemOut]

# --- Helpers ---
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _hash_secret(secret: str) -> str:
    salt = secrets.token_hex(8)
    return f"sha256:{salt}:{_sha256(salt+secret)}"

def _check_secret(secret: str, secret_hash: str) -> bool:
    try:
        _algo, salt, digest = secret_hash.split(":", 2)
        return hmac.compare_digest(_sha256(salt+secret), digest)
    except Exception:
        return False

def _sign_link(data: str, exp: datetime) -> str:
    payload = f"{data}.{int(exp.timestamp())}"
    sig = hmac.new(SESSION_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"

def _verify_link(token: str, now: Optional[datetime] = None) -> Optional[Dict[str,str]]:
    now = now or _utcnow()
    try:
        data, exp_ts, sig = token.rsplit(".", 2)
        exp = datetime.fromtimestamp(int(exp_ts), tz=timezone.utc)
        if now > exp:
            return None
        expected = hmac.new(SESSION_SECRET, f"{data}.{exp_ts}".encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        return {"id": data, "exp": exp_ts}
    except Exception:
        return None

def _ensure_not_expired(row: Dict[str, Any]) -> None:
    if row.get("deleted_at"):
        raise HTTPException(status_code=404, detail="arquivo não encontrado")
    expires_at = row.get("expires_at")
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at.replace("Z","+00:00"))
    if expires_at and _utcnow() > expires_at:
        raise HTTPException(status_code=404, detail="arquivo expirado")

def _owner_match(row: Dict[str, Any], user: Dict[str, Any]) -> bool:
    return (row.get("owner_id") and user and str(row.get("owner_id")) == str(user.get("cpf")))

def _is_super(user: Optional[Dict[str, Any]]) -> bool:
    return bool((user or {}).get("is_superuser"))

def _save_stream(dest: Path, up: UploadFile) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with dest.open("wb") as f:
        while True:
            chunk = up.file.read(1024*1024)
            if not chunk:
                break
            f.write(chunk)
            size += len(chunk)
    return size

# --- UI ---
@router.get("/ui", response_class=HTMLResponse)
def get_ui(request: Request):
    return templates.TemplateResponse("fileshare/ui.html", {"request": request})

@router.get("/schema")
def get_schema():
    return {
        "POST /submit": {"fields": {"file":"binary", "ttl":"1d|7d|30d", "secret":"(opcional)"}},
        "GET /items": {"query": ["owner=(me|all)", "limit", "offset", "q"]},
        "POST /items/{id}/download": {"body": {"secret":"(opcional; exigido se protegido, exceto superuser)"}},
        # Regras:
        # - protegido (com senha): só o DONO pode gerar link e precisa informar a senha correta (superuser pode gerar sem senha)
        # - público (sem senha): qualquer usuário autenticado pode gerar link
        "POST /items/{id}/share": {"body": {"expires":"1d|7d|30d", "secret":"(obrigatória se protegido, exceto superuser)"}},
        "POST /items/{id}/delete": {"owner ou admin"},
    }

# --- Endpoints núcleo ---
@router.post("/submit", response_model=ItemOut)
async def upload(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    ttl: str = Form("7d"),
    secret: Optional[str] = Form(None),
):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    ttl = ttl if ttl in TTL_MAP else "7d"
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
        actor=user, action="uploaded", kind="fileshare", target_id=item_id,
        meta={"filename": file.filename, "size": size, "ttl": ttl, "has_secret": bool(secret)}
    )

    background.add_task(db.fileshare_cleanup_expired, limit=200)

    return {
        "id": item_id, "filename": file.filename, "size": size, "content_type": file.content_type,
        "owner_id": rec["owner_id"], "owner_name": rec["owner_name"],
        "created_at": datetime.fromisoformat(rec["created_at"]),
        "expires_at": datetime.fromisoformat(rec["expires_at"]),
        "has_secret": bool(secret_hash), "downloads": 0, "deleted_at": None
    }

@router.get("/items", response_model=Page)
def list_items(
    request: Request,
    owner: str = Query("all", pattern="^(all|me)$"),
    q: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    rows = db.fileshare_list(owner_id=user.get("cpf") if owner=="me" else None, q=q, limit=limit, offset=offset)
    items: List[Dict[str, Any]] = []
    for r in rows:
        try:
            _ensure_not_expired(r)
        except HTTPException:
            continue
        items.append({
            "id": r["id"], "filename": r["filename"], "size": r["size"], "content_type": r.get("content_type"),
            "owner_id": r.get("owner_id"), "owner_name": r.get("owner_name"),
            "created_at": r["created_at"], "expires_at": r["expires_at"],
            "has_secret": bool(r.get("secret_hash")), "downloads": r.get("downloads") or 0,
            "deleted_at": r.get("deleted_at"),
        })
    return {"count": len(items), "items": items}

@router.post("/items/{item_id}/download")
def download_item(item_id: str, request: Request, secret: Optional[str] = Form(None)):
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
            db.audit_log(actor=user, action="download_denied", kind="fileshare", target_id=item_id, meta={"reason":"secret_required"})
            raise HTTPException(status_code=403, detail="chave secreta inválida ou ausente")

    path = Path(r["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="arquivo indisponível")

    db.fileshare_inc_downloads(item_id)
    db.audit_log(
        actor=user,
        action="downloaded",
        kind="fileshare",
        target_id=item_id,
        meta={"filename": r["filename"], "superuser_override": superuser and bool(secret_hash)}
    )

    def _iterfile():
        with path.open("rb") as f:
            while chunk := f.read(1024*1024):
                yield chunk

    headers = {"Content-Disposition": f'attachment; filename="{r["filename"]}"'}
    return StreamingResponse(_iterfile(), media_type=r.get("content_type") or "application/octet-stream", headers=headers)

@router.post("/items/{item_id}/share")
def create_share_link(
    item_id: str,
    request: Request,
    expires: str = Form("7d"),
    secret: Optional[str] = Form(None),
):
    """
    Regras:
      - Item protegido (com senha): somente o DONO pode gerar link e deve informar a senha correta.
        *Superuser pode gerar link para qualquer item (sem precisar da senha).*
      - Item público (sem senha): qualquer usuário autenticado pode gerar link.
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
        # superuser pode tudo; caso contrário, apenas dono + senha correta
        if not superuser:
            if not _owner_match(r, user):
                db.audit_log(actor=user, action="share_link_denied", kind="fileshare", target_id=item_id, meta={"reason":"not_owner_protected"})
                raise HTTPException(status_code=403, detail="apenas o dono pode gerar link para arquivo protegido")
            if not secret or not _check_secret(secret, r["secret_hash"]):
                db.audit_log(actor=user, action="share_link_denied", kind="fileshare", target_id=item_id, meta={"reason":"invalid_secret"})
                raise HTTPException(status_code=403, detail="senha requerida para gerar link")
    # público: qualquer autenticado pode gerar link (sem checagens adicionais)

    ttl = TTL_MAP.get(expires, TTL_MAP["7d"])
    exp = _utcnow() + ttl
    token = _sign_link(r["id"], exp)

    db.audit_log(
        actor=user,
        action="shared_link_created",
        kind="fileshare",
        target_id=item_id,
        meta={"expires": exp.isoformat(), "public": not protected, "superuser_override": superuser and protected}
    )
    return {"download_url": f"/api/automations/fileshare/share/{token}"}

@router.get("/share/{token}")
def share_download(token: str):
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
    db.audit_log(actor={"cpf":"anonymous"}, action="downloaded_shared_link", kind="fileshare", target_id=item_id, meta={"via":"token"})

    def _iterfile():
        with path.open("rb") as f:
            while chunk := f.read(1024*1024):
                yield chunk

    headers = {"Content-Disposition": f'attachment; filename="{r["filename"]}"'}
    return StreamingResponse(_iterfile(), media_type=r.get("content_type") or "application/octet-stream", headers=headers)

@router.post("/items/{item_id}/delete")
def delete_item(item_id: str, request: Request, background: BackgroundTasks):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")

    r = db.fileshare_get(item_id)
    if not r:
        raise HTTPException(status_code=404, detail="arquivo não encontrado")
    if not (_owner_match(r, user) or "admin" in (user.get("roles") or [])):
        raise HTTPException(status_code=403, detail="forbidden")

    db.fileshare_soft_delete(item_id)
    db.audit_log(actor=user, action="deleted", kind="fileshare", target_id=item_id, meta={"filename": r["filename"]})

    p = Path(r["path"])
    if p.exists():
        background.add_task(lambda: p.unlink(missing_ok=True))
    return {"ok": True}

@router.post("/tasks/cleanup")
def cleanup_now(limit: int = 200):
    deleted = db.fileshare_cleanup_expired(limit=limit)
    return {"expired_deleted": deleted}
