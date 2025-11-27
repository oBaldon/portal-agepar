# apps/bff/app/automations/controle_ferias.py
from __future__ import annotations

"""
Automação de Controle de Férias — Portal AGEPAR.

Propósito
---------
Normaliza submissões do tipo "ferias" em eventos padronizados e expõe:
- UI HTML para visualização.
- API JSON (`/events`) para consulta de eventos com filtros.
- Exportações em CSV (`/events.csv`) e iCalendar (`/events.ics`).

Segurança
---------
Todos os endpoints são protegidos por RBAC e exigem pelo menos um dos papéis:
`"coordenador"` ou `"admin"`.

Detalhes de implementação
-------------------------
- As submissões podem conter um período simples (inicio/fim) ou uma lista
  `periodos[]`. Ambas as formas são suportadas.
- Datas de término nos eventos são tratadas como inclusivas. Para iCal (padrão
  end-exclusive), o término é convertido para o dia seguinte.
"""

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
    dependencies=[Depends(require_roles_any("coordenador", "admin"))],
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


class Filtro(BaseModel):
    """
    Filtros de consulta para eventos de férias.

    Atributos
    ---------
    since : Optional[datetime]
        Inclui eventos que terminam em ou após esta data/hora.
    until : Optional[datetime]
        Inclui eventos que começam em ou antes desta data/hora.
    servidor : Optional[str]
        Filtro de substring (case-insensitive) sobre o nome do servidor.
    setor : Optional[str]
        Filtro de substring (case-insensitive) sobre o setor.
    status : Optional[str]
        Filtro por status exato (case-insensitive).
    limit : int
        Limite superior de eventos retornados após filtragem.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    since: Optional[datetime] = None
    until: Optional[datetime] = None
    servidor: Optional[str] = None
    setor: Optional[str] = None
    status: Optional[str] = None
    limit: int = Field(default=2000, ge=1, le=10000)


class EventoFerias(BaseModel):
    """
    Representação normalizada de um evento de férias.

    Atributos
    ---------
    id : str
        Identificador único (submission_id#index).
    servidor : str
        Nome do servidor.
    matricula : Optional[str]
        Matrícula ou SIAPE.
    setor : Optional[str]
        Diretoria/unidade/setor.
    status : Optional[str]
        Status textual associado à submissão.
    start : str
        Data inicial inclusiva no formato YYYY-MM-DD.
    end : str
        Data final inclusiva no formato YYYY-MM-DD.
    obs : Optional[str]
        Observações livres.
    colorKey : Optional[str]
        Chave de cor para diferenciação visual (ex.: e-mail/CPF).
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    id: str
    servidor: str
    matricula: Optional[str] = None
    setor: Optional[str] = None
    status: Optional[str] = None
    start: str
    end: str
    obs: Optional[str] = None
    colorKey: Optional[str] = None


def _to_obj(x: Any) -> Dict[str, Any]:
    """
    Converte diferentes tipos (dict, JSON em str/bytes) para `dict`.

    Retorna um dict vazio quando a conversão não é possível.
    """
    if isinstance(x, dict):
        return x
    if x is None:
        return {}
    if isinstance(x, (bytes, bytearray)):
        try:
            return json.loads(x.decode("utf-8"))
        except Exception:
            return {}
    if isinstance(x, str):
        try:
            return json.loads(x)
        except Exception:
            return {}
    return {}


def _norm_date(v: Any) -> Optional[date]:
    """
    Normaliza valores diversos para `date`.

    Aceita `date`, `datetime`, ou strings ISO (com/sem timezone).
    Retorna `None` quando não for possível interpretar.
    """
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    s = str(v).strip()
    if not s:
        return None
    try:
        if "T" in s or " " in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


def _text(x: Any) -> str:
    """Converte valores para `str` aparada; retorna string vazia para nulos."""
    return str(x or "").strip()


def _match_contains(hay: str, needle: str) -> bool:
    """Compara inclusão de substring de forma case-insensitive."""
    return needle.lower() in hay.lower()


def _explode_periodos(sub: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extrai 1..N períodos de uma submissão.

    Prioriza `periodos[]` no payload/resultado; caso ausente, tenta chaves simples
    `inicio`/`fim` (ou `data_inicio`/`data_fim`). Cada item produzido contém:
    - `inicio`, `fim`, `obs`, `idx`.
    """
    payload = _to_obj(sub.get("payload"))
    result = _to_obj(sub.get("result"))
    candidates: List[Dict[str, Any]] = []

    per = payload.get("periodos") or result.get("periodos")
    if isinstance(per, list):
        for i, p in enumerate(per):
            if not isinstance(p, dict):
                continue
            candidates.append(
                {
                    "inicio": p.get("inicio") or p.get("data_inicio"),
                    "fim": p.get("fim") or p.get("data_fim"),
                    "obs": p.get("obs") or p.get("observacao"),
                    "idx": i,
                }
            )

    if not candidates:
        candidates.append(
            {
                "inicio": payload.get("inicio")
                or payload.get("data_inicio")
                or result.get("inicio"),
                "fim": payload.get("fim") or payload.get("data_fim") or result.get("fim"),
                "obs": payload.get("obs") or result.get("obs"),
                "idx": 0,
            }
        )

    return candidates


def _build_eventos(sub: Dict[str, Any]) -> List[EventoFerias]:
    """
    Converte uma submissão (kind='ferias') em 1..N `EventoFerias`.

    Regras
    ------
    - Corrige inversão de datas quando `fim < inicio`.
    - Datas `end` permanecem inclusivas (o iCal fará +1 dia).
    """
    payload = _to_obj(sub.get("payload"))
    result = _to_obj(sub.get("result"))

    servidor = _text(
        payload.get("servidor") or payload.get("nome") or sub.get("actor_nome") or sub.get("username")
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
            di, df = df, di
        eventos.append(
            EventoFerias(
                id=f"{sub.get('id')}#{per.get('idx', 0)}",
                servidor=servidor,
                matricula=matricula or None,
                setor=setor or None,
                status=status or None,
                start=di.isoformat(),
                end=df.isoformat(),
                obs=_text(per.get("obs")) or None,
                colorKey=color_key or None,
            )
        )
    return eventos


def _apply_filters(items: List[EventoFerias], f: Filtro) -> List[EventoFerias]:
    """
    Aplica filtros de janela temporal e texto aos eventos.

    Critérios
    ---------
    - Intervalo: inclui eventos que interceptam [since, until].
    - Texto: `servidor`/`setor` por substring; `status` por igualdade (case-insensitive).
    - Limite: interrompe ao atingir `f.limit`.
    """
    def in_range(ev: EventoFerias) -> bool:
        di = _norm_date(ev.start)
        df = _norm_date(ev.end)
        if f.since and df and df < f.since.date():
            return False
        if f.until and di and di > f.until.date():
            return False
        return True

    out: List[EventoFerias] = []
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


@router.get("/ui", response_class=HTMLResponse)
def get_ui(request: Request):
    """
    Retorna a página HTML (Jinja2) da visualização de férias.
    """
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
    """
    Lista eventos normalizados de férias com filtros opcionais.

    Retorna
    -------
    dict
        `{"count": int, "items": List[EventoFerias as dict]}`
    """
    try:
        try:
            subs = db.list_submissions_admin(
                kind="ferias",
                username=None,
                status=None,
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
    """
    Exporta os eventos filtrados em CSV.

    Cabeçalho
    ---------
    id, servidor, matricula, setor, status, inicio, fim, obs
    """
    data = list_events(since=since, until=until, servidor=servidor, setor=setor, status=status, limit=limit)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "servidor", "matricula", "setor", "status", "inicio", "fim", "obs"])
    for it in data["items"]:
        w.writerow(
            [
                it["id"],
                it["servidor"],
                it.get("matricula", ""),
                it.get("setor", ""),
                it.get("status", ""),
                it["start"],
                it["end"],
                (it.get("obs") or ""),
            ]
        )
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
    """
    Gera arquivo iCalendar (VCALENDAR) com um VEVENT por período.

    Regras
    ------
    - DTSTART e DTEND são `VALUE=DATE`.
    - `end` é inclusivo nos dados; para o iCal é convertido para end-exclusive (+1 dia).
    """
    data = list_events(since=since, until=until, servidor=servidor, setor=setor, status=status, limit=limit)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Portal AGEPAR//Controle Férias//PT-BR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for it in data["items"]:
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
        desc_text = "\\n".join(desc_parts)
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
