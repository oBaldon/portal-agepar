from __future__ import annotations

import html as html_lib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_SIGNATURE_PATH = Path("/app/app/integrations/signatures/plataforma_agepar.html")


def plain_to_html(text: str) -> str:
    escaped = html_lib.escape(text or "").replace("\n", "<br>\n")
    return (
        '<div style="font-family: Arial, sans-serif; font-size: 12pt; line-height: 1.35;">'
        f"{escaped}"
        "</div>"
    )


def load_signature_html() -> str:
    if not _SIGNATURE_PATH.exists():
        logger.warning(
            "[EMAIL_TEMPLATES] Assinatura não encontrada em %s",
            _SIGNATURE_PATH,
        )
        return ""

    try:
        return _SIGNATURE_PATH.read_text(encoding="utf-8", errors="replace").strip()
    except Exception as exc:
        logger.error(
            "[EMAIL_TEMPLATES] Falha ao ler assinatura em %s | error=%s",
            _SIGNATURE_PATH,
            exc,
        )
        return ""


def build_notification_email_html(body_plain: str) -> str:
    base_html = plain_to_html(body_plain)
    signature_html = load_signature_html()

    if not signature_html:
        return base_html

    return f"{base_html}<br><br>\n{signature_html}"