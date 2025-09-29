from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field

from app.auth.rbac import require_roles_any
from app import db as db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/automations/controle/ferias",
    tags=["automations", "controle", "ferias"],
    # coordenador/admin (e opcionalmente rh)
    dependencies=[Depends(require_roles_any("coordenador", "admin"))],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# -------- Models --------
class Filtro(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    servidor: Optional[str] = None
    setor: Optional[str] = None
    status: Optional[str] = None
    limit: int = Field(default=2000, ge=1, le=10000)

class EventoFerias(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    id: str
    servidor: str
    matricula: Optional[str] = None
    setor: Optional[str] = None
    status: Optional[str] = None
    start: str  # YYYY-MM-DD (inclusive)
    end: str    # YYYY-MM-DD (inclusive)
    obs: Optional[str] = None
    colorKey: Optional[str] = None

# -------- Helpers --------
def _to_obj(x: Any) -> Dict[str, Any]:
    if isinstance(x, dict): return x
    if x is None: return {}
    if isinstance(x, (bytes, bytearray)):
        try: return json.loads(x.decode("utf-8"))
        except Exception: return {}
    if isinstance(x, str):
        try: return json.loads(x)
        except Exception: return {}
    return {}

def _norm_date(v: Any) -> Optional[date]:
    if v is None: return None
    if isinstance(v, date) and not isinstance(v, datetime): return v
    if isinstance(v, datetime): return v.date()
    s = str(v).strip()
    if not s: return None
    # aceita YYYY-MM-DD e ISO
    try:
        if "T" in s or " " in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return datetime.fromisoformat(s).date()
    except Exception:
        return None

def _text(x: Any) -> str:
    return str(x or "").strip()

def _match_contains(hay: str, needle: str) -> bool:
    return needle.lower() in hay.lower()

def _explode_periodos(sub: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Aceita estrutura simples (inicio/fim) ou array periodos[]."""
    payload = _to_obj(sub.get("payload"))
    result = _to_obj(sub.get("result"))
    # candidatos de período
    candidates: List[Dict[str, Any]] = []

    # 1) array de periodos
    per = payload.get("periodos") or result.get("periodos")
    if isinstance(per, list):
        for i, p in enumerate(per):
            if not isinstance(p, dict): continue
            candidates.append({
                "inicio": p.get("inicio") or p.get("data_inicio"),
                "fim": p.get("fim") or p.get("data_fim"),
                "obs": p.get("obs") or p.get("observacao"),
                "idx": i,
            })

    # 2) período simples
    if not candidates:
        candidates.append({
            "inicio": payload.get("inicio") or payload.get("data_inicio") or result.get("inicio"),
            "fim": payload.get("fim") or payload.get("data_fim") or result.get("fim"),
            "obs": payload.get("obs") or result.get("obs"),
            "idx": 0,
        })

    return candidates

def _build_eventos(sub: Dict[str, Any]) -> List[EventoFerias]:
    """Normaliza uma submission (kind=ferias) em 1..N eventos."""
    payload = _to_obj(sub.get("payload"))
    result = _to_obj(sub.get("result"))

    servidor = _text(
        payload.get("servidor") or payload.get("nome") or
        sub.get("actor_nome") or sub.get("username")
    )
    matricula = _text(payload.get("matricula") or payload.get("siape"))
    setor = _text(payload.get("setor") or payload.get("diretoria") or payload.get("unidade"))
    status = _text(sub.get("status") or result.get("status") or payload.get("status"))
    color_key = _text(payload.get("email") or payload.get("cpf") or servidor or matricula)

    eventos: List[EventoFerias] = []
    for per in _explode_periodos(sub):
        di = _norm_date(per.get("inicio"))
        df = _norm_date(per.get("fim"))
        if not di or not df:
            continue
        if df < di:
            di, df = df, di  # corrige inversão

        eventos.append(EventoFerias(
            id=f"{sub.get('id')}#{per.get('idx',0)}",
            servidor=servidor,
            matricula=matricula or None,
            setor=setor or None,
            status=status or None,
            start=di.isoformat(),
            end=df.isoformat(),  # inclusive (vamos +1 no ICS)
            obs=_text(per.get("obs")) or None,
            colorKey=color_key or None,
        ))
    return eventos

def _apply_filters(items: List[EventoFerias], f: Filtro) -> List[EventoFerias]:
    def in_range(ev: EventoFerias) -> bool:
        di = _norm_date(ev.start)
        df = _norm_date(ev.end)
        if f.since and df and df < f.since.date():   # tudo antes do since
            return False
        if f.until and di and di > f.until.date():   # tudo depois do until
            return False
        return True

    out = []
    for it in items:
        if f.servidor and not _match_contains(it.servidor, f.servidor):
            continue
        if f.setor and not _match_contains(it.setor or "", f.setor):
            continue
        if f.status and (it.status or "").lower() != f.status.lower():
            continue
        if not in_range(it):
            continue
        out.append(it)
        if len(out) >= f.limit:
            break
    return out

# -------- Endpoints --------
@router.get("/ui", response_class=HTMLResponse)
def get_ui(request: Request):
    return templates.TemplateResponse("controle_ferias/ui.html", {"request": request})

@router.get("/events")
def list_events(
    since: Optional[datetime] = Query(default=None),
    until: Optional[datetime] = Query(default=None),
    servidor: Optional[str] = Query(default=None),
    setor: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=2000, ge=1, le=10000),
):
    try:
        try:
            subs = db.list_submissions_admin(
                kind="ferias",
                username=None,  # não filtra por ator neste endpoint
                status=None,    # usamos 'status' apenas para filtrar visualização
                limit=limit,
                offset=0,
            )
        except AttributeError:
            raise HTTPException(status_code=500, detail="list_submissions_admin(kind='ferias') indisponível.")

        eventos: List[EventoFerias] = []
        for sub in subs:
            eventos.extend(_build_eventos(sub))

        f = Filtro(since=since, until=until, servidor=servidor, setor=setor, status=status, limit=limit)
        items = _apply_filters(eventos, f)
        return {"count": len(items), "items": [e.model_dump() for e in items]}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro ao listar eventos de férias")
        raise HTTPException(status_code=500, detail=f"erro ao listar eventos: {e}")

@router.get("/events.csv")
def events_csv(
    since: Optional[datetime] = Query(default=None),
    until: Optional[datetime] = Query(default=None),
    servidor: Optional[str] = Query(default=None),
    setor: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=50000),
):
    data = list_events(since=since, until=until, servidor=servidor, setor=setor, status=status, limit=limit)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id","servidor","matricula","setor","status","inicio","fim","obs"])
    for it in data["items"]:
        w.writerow([it["id"], it["servidor"], it.get("matricula",""), it.get("setor",""), it.get("status",""),
                    it["start"], it["end"], (it.get("obs") or "")])
    out = buf.getvalue().encode("utf-8")
    headers = {"Content-Disposition": 'attachment; filename="ferias.csv"'}
    return StreamingResponse(io.BytesIO(out), media_type="text/csv; charset=utf-8", headers=headers)

@router.get("/events.ics")
def events_ics(
    since: Optional[datetime] = Query(default=None),
    until: Optional[datetime] = Query(default=None),
    servidor: Optional[str] = Query(default=None),
    setor: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=50000),
):
    """Gera iCal com VEVENT por período (end-exclusive conforme padrão iCal)."""
    data = list_events(since=since, until=until, servidor=servidor, setor=setor, status=status, limit=limit)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Portal AGEPAR//Controle Férias//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for it in data["items"]:
        # start inclusive; end-exclusive (+1 dia)
        dt_start = _norm_date(it["start"]) or date.today()
        dt_end_inc = _norm_date(it["end"]) or dt_start
        dt_end_ex = dt_end_inc + timedelta(days=1)
        uid = f"{it['id']}@portal-agepar"
        summary = f"Férias — {it['servidor']}"
        desc_parts: List[str] = []
        if it.get("setor"):
            desc_parts.append(f"Setor: {it['setor']}")
        if it.get("status"):
            desc_parts.append(f"Status: {it['status']}")
        if it.get("obs"):
            desc_parts.append(f"Obs: {it['obs']}")
        desc_text = "\\n".join(desc_parts)  # ICS usa \n dentro do DESCRIPTION
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"SUMMARY:{summary}",
            f"DTSTART;VALUE=DATE:{dt_start.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{dt_end_ex.strftime('%Y%m%d')}",
            f"DESCRIPTION:{desc_text}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    body = "\r\n".join(lines)
    headers = {"Content-Disposition": 'attachment; filename=\"ferias.ics\"'}
    return PlainTextResponse(content=body, media_type="text/calendar; charset=utf-8", headers=headers)
