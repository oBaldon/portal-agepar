from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Any, Mapping, Optional, Sequence

import httpx

logger = logging.getLogger(__name__)

AttachmentPayload = Mapping[str, Any]


def _is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


class ExpressoMailError(RuntimeError):
    """Erro de integração com a API do Expresso."""


class ExpressoMailAuthError(ExpressoMailError):
    """Erro de autenticação/autorização na API do Expresso."""


def _extract_error_payload(payload: Any) -> Optional[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return None

    err = payload.get("error")
    if isinstance(err, Mapping):
        return dict(err)

    code = payload.get("code")
    message = payload.get("message")
    if code is not None and message:
        return {"code": code, "message": message}

    result = payload.get("result")
    if isinstance(result, Mapping):
        nested_err = result.get("error")
        if isinstance(nested_err, Mapping):
            return dict(nested_err)
        nested_code = result.get("code")
        nested_message = result.get("message")
        if nested_code is not None and nested_message:
            return {"code": nested_code, "message": nested_message}

    return None


class ExpressoMailClient:
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        auth_cache_seconds: Optional[int] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv("EXPRESSO_API_BASE", "https://api-slim.expresso.pr.gov.br/celepar")
        ).strip().rstrip("/")
        self.username = (username or os.getenv("EXPRESSO_API_USER", "")).strip()
        self.password = password if password is not None else os.getenv("EXPRESSO_API_PASSWORD", "")
        self.timeout_seconds = float(timeout_seconds or os.getenv("EXPRESSO_MAIL_TIMEOUT_SECONDS", "20"))
        self.auth_cache_seconds = int(auth_cache_seconds or os.getenv("EXPRESSO_MAIL_AUTH_CACHE_SECONDS", "600"))
        if enabled is None:
            enabled = _is_truthy(os.getenv("EXPRESSO_MAIL_ENABLED", "false"))
        self._enabled = bool(enabled)

        self._lock = threading.Lock()
        self._auth_token: Optional[str] = None
        self._auth_expires_at: float = 0.0
        self._rpc_id = 100

    @property
    def enabled(self) -> bool:
        return self._enabled and bool(self.base_url and self.username and self.password)

    def _next_rpc_id(self) -> int:
        with self._lock:
            self._rpc_id += 1
            return self._rpc_id

    def invalidate_auth(self) -> None:
        with self._lock:
            self._auth_token = None
            self._auth_expires_at = 0.0

    def _post_json_rpc(self, route: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/{route.lstrip('/')}"
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.post(
                    url,
                    json=dict(payload),
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            body = exc.response.text[:1000] if exc.response is not None else ""
            raise ExpressoMailError(f"HTTP {status} calling Expresso: {body}") from exc
        except httpx.HTTPError as exc:
            raise ExpressoMailError(f"HTTP error calling Expresso: {exc}") from exc

        try:
            payload_json = response.json()
        except ValueError as exc:
            raise ExpressoMailError(f"Expresso returned a non-JSON response on {route}") from exc

        err = _extract_error_payload(payload_json)
        if err:
            code = err.get("code")
            message = str(err.get("message") or "unknown error")
            if code in {2, 3, 5, 7, 200, "2", "3", "5", "7", "200"}:
                raise ExpressoMailAuthError(f"Expresso auth error {code}: {message}")
            raise ExpressoMailError(f"Expresso API error {code}: {message}")

        return dict(payload_json)

    def _post_form_rpc(
        self,
        route: str,
        params: Mapping[str, Any],
        *,
        attachments: Optional[Sequence[AttachmentPayload]] = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}/{route.lstrip('/')}"
        payload = {
            "id": str(self._next_rpc_id()),
            "params": json.dumps(dict(params), ensure_ascii=False),
        }

        files = []
        for attachment in attachments or ():
            filename = str(attachment.get("filename") or "").strip()
            if not filename:
                raise ExpressoMailError("attachment filename is required")
            content = attachment.get("content")
            if content is None:
                raise ExpressoMailError(f"attachment content is required ({filename})")
            if isinstance(content, str):
                content = content.encode("utf-8")
            content_type = str(attachment.get("content_type") or "application/octet-stream").strip()
            files.append(("attachments[]", (filename, content, content_type)))
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.post(
                    url,
                    data=payload,
                    files=files or None,
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            body = exc.response.text[:1000] if exc.response is not None else ""
            raise ExpressoMailError(f"HTTP {status} calling Expresso: {body}") from exc
        except httpx.HTTPError as exc:
            raise ExpressoMailError(f"HTTP error calling Expresso: {exc}") from exc

        try:
            payload_json = response.json()
        except ValueError as exc:
            raise ExpressoMailError(f"Expresso returned a non-JSON response on {route}") from exc

        err = _extract_error_payload(payload_json)
        if err:
            code = err.get("code")
            message = str(err.get("message") or "unknown error")
            if code in {2, 3, 7, "2", "3", "7"}:
                raise ExpressoMailAuthError(f"Expresso auth error {code}: {message}")
            raise ExpressoMailError(f"Expresso API error {code}: {message}")

        return dict(payload_json)

    def _get_auth_token(self, *, force_refresh: bool = False) -> str:
        now = time.time()
        with self._lock:
            if not force_refresh and self._auth_token and now < self._auth_expires_at:
                return self._auth_token

        payload = self._post_json_rpc(
            "/Login",
            {
                "id": self._next_rpc_id(),
                "params": {
                    "user": self.username,
                    "password": self.password,
                },
            },
        )

        auth = ((payload.get("result") or {}) if isinstance(payload, Mapping) else {}).get("auth")
        if not auth or not str(auth).strip():
            raise ExpressoMailError(f"Login sem auth no retorno: {payload}")

        with self._lock:
            self._auth_token = str(auth).strip()
            self._auth_expires_at = time.time() + max(30, self.auth_cache_seconds)
            return self._auth_token

    def send_mail(
        self,
        *,
        to: str | Sequence[str],
        subject: str,
        body: str,
        msg_type: str = "plain",
        attachments: Optional[Sequence[AttachmentPayload]] = None,
    ) -> dict[str, Any]:
        recipients = [to] if isinstance(to, str) else [item for item in to if str(item or "").strip()]
        recipients = [str(item).strip() for item in recipients if str(item or "").strip()]

        if not recipients:
            raise ExpressoMailError("at least one recipient is required")
        if not self.enabled:
            raise ExpressoMailError("Expresso mail integration is disabled or incomplete")

        def _send(auth_token: str) -> dict[str, Any]:
            payload = self._post_form_rpc(
                "/Mail/Send",
                {
                    "auth": auth_token,
                    "msgTo": ",".join(recipients),
                    "msgSubject": subject,
                    "msgBody": body,
                    "msgType": msg_type,
                },
                attachments=attachments,
            )
            if payload.get("result") is not True:
                raise ExpressoMailError(f"Expresso Mail/Send sem sucesso explicito: {payload}")
            return payload

        auth_token = self._get_auth_token()
        try:
            return _send(auth_token)
        except ExpressoMailAuthError:
            logger.warning("[EXPRESSO] Token auth expirado/invalido; renovando e reenviando.")
            self.invalidate_auth()
            return _send(self._get_auth_token(force_refresh=True))


_default_client: Optional[ExpressoMailClient] = None
_default_lock = threading.Lock()


def get_expresso_mail_client() -> ExpressoMailClient:
    global _default_client
    with _default_lock:
        if _default_client is None:
            _default_client = ExpressoMailClient()
        return _default_client