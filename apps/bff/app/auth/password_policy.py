from __future__ import annotations

"""
Password Policy — Portal AGEPAR (BFF)

Objetivo
--------
Validar novas senhas de forma padronizada e configurável por ambiente, com
mensagens legíveis e fáceis de exibir no frontend.

Como usar (exemplo no routes.py)
--------------------------------
from .password_policy import evaluate_password, enforce_password_policy

errors = evaluate_password(new_password, identifiers=[email, cpf, nome])
if errors:
    # 422 Unprocessable Entity (ou 400, a critério)
    raise HTTPException(status_code=422, detail={"password": errors})

# ou
enforce_password_policy(new_password, identifiers=[email, cpf])

Parâmetros via ENV
------------------
- AUTH_PASSWORD_POLICY_MIN_LENGTH           (int, default=8)
- AUTH_PASSWORD_POLICY_REQUIRE_DIGIT        (bool, default=true)
- AUTH_PASSWORD_POLICY_REQUIRE_LETTER       (bool, default=true)
- AUTH_PASSWORD_POLICY_REQUIRE_UPPER        (bool, default=false)
- AUTH_PASSWORD_POLICY_REQUIRE_LOWER        (bool, default=false)
- AUTH_PASSWORD_POLICY_REQUIRE_SPECIAL      (bool, default=false)
- AUTH_PASSWORD_POLICY_DISALLOW_WHITESPACE  (bool, default=true)
- AUTH_PASSWORD_POLICY_FORBID_COMMON        (bool, default=true)
- AUTH_PASSWORD_POLICY_BLOCK_IDENTIFIERS    (bool, default=true)  # evita conter email/cpf/nome
- AUTH_PASSWORD_POLICY_MIN_DIFF_CHARS       (int, default=4)      # diversidade mínima de caracteres distintos
"""

import os
import re
from typing import Iterable, List, Optional, Tuple


def _env_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "y", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


# === Config (lida uma vez, mas simples o suficiente para permanecer aqui) ===
MIN_LENGTH = _env_int("AUTH_PASSWORD_POLICY_MIN_LENGTH", 8)
REQUIRE_DIGIT = _env_bool("AUTH_PASSWORD_POLICY_REQUIRE_DIGIT", True)
REQUIRE_LETTER = _env_bool("AUTH_PASSWORD_POLICY_REQUIRE_LETTER", True)
REQUIRE_UPPER = _env_bool("AUTH_PASSWORD_POLICY_REQUIRE_UPPER", False)
REQUIRE_LOWER = _env_bool("AUTH_PASSWORD_POLICY_REQUIRE_LOWER", False)
REQUIRE_SPECIAL = _env_bool("AUTH_PASSWORD_POLICY_REQUIRE_SPECIAL", False)
DISALLOW_WHITESPACE = _env_bool("AUTH_PASSWORD_POLICY_DISALLOW_WHITESPACE", True)
FORBID_COMMON = _env_bool("AUTH_PASSWORD_POLICY_FORBID_COMMON", True)
BLOCK_IDENTIFIERS = _env_bool("AUTH_PASSWORD_POLICY_BLOCK_IDENTIFIERS", True)
MIN_DIFF_CHARS = _env_int("AUTH_PASSWORD_POLICY_MIN_DIFF_CHARS", 4)

# Caracteres especiais aceitos (ajuste se necessário)
SPECIAL_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
DIGIT_RE = re.compile(r"\d")
LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
UPPER_RE = re.compile(r"[A-ZÁÉÍÓÚÂÊÎÔÛÀÈÌÒÙÃÕÇ]")
LOWER_RE = re.compile(r"[a-záéíóúâêîôûàèìòùãõç]")

CPF_ONLY_DIGITS_RE = re.compile(r"^\d{11}$")

# Lista curta de senhas comuns (não exaustiva, mas cobre casos clássicos)
COMMON_PASSWORDS = {
    "123456", "12345678", "123456789", "senha", "password", "qwerty", "abc123",
    "111111", "123123", "000000", "iloveyou", "admin",
}


def _normalize_identifier(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = s.strip().lower()
    # Remove separadores visuais frequentes em CPF/telefone
    s = re.sub(r"[.\-_/()\s]", "", s)
    return s or None


def _contains_identifier(pwd: str, identifiers: Iterable[Optional[str]]) -> bool:
    pwd_l = pwd.lower()
    for raw in identifiers or []:
        ident = _normalize_identifier(raw)
        if not ident:
            continue
        if ident and len(ident) >= 3 and ident in pwd_l:
            return True
        # Para CPF (11 dígitos) — bloquear se o CPF aparecer exatamente
        if CPF_ONLY_DIGITS_RE.fullmatch(ident) and ident in pwd_l:
            return True
    return False


def evaluate_password(new_password: str, *, identifiers: Optional[Iterable[Optional[str]]] = None) -> List[str]:
    """
    Avalia a senha e retorna uma lista de mensagens de erro (em pt-BR).
    Se a lista vier vazia => senha aprovada pela política.
    """
    errors: List[str] = []
    pwd = new_password or ""

    # Tamanho mínimo
    if len(pwd) < MIN_LENGTH:
        errors.append(f"A senha deve ter pelo menos {MIN_LENGTH} caracteres.")

    # Espaços em branco
    if DISALLOW_WHITESPACE and any(ch.isspace() for ch in pwd):
        errors.append("A senha não pode conter espaços em branco.")

    # Diversidade mínima
    if MIN_DIFF_CHARS > 0 and len(set(pwd)) < MIN_DIFF_CHARS:
        errors.append(f"A senha deve possuir ao menos {MIN_DIFF_CHARS} caracteres distintos.")

    # Dígitos/letras/maiúsculas/minúsculas/especiais
    if REQUIRE_DIGIT and not DIGIT_RE.search(pwd):
        errors.append("A senha deve conter pelo menos 1 dígito (0–9).")
    if REQUIRE_LETTER and not LETTER_RE.search(pwd):
        errors.append("A senha deve conter pelo menos 1 letra.")
    if REQUIRE_UPPER and not UPPER_RE.search(pwd):
        errors.append("A senha deve conter pelo menos 1 letra maiúscula.")
    if REQUIRE_LOWER and not LOWER_RE.search(pwd):
        errors.append("A senha deve conter pelo menos 1 letra minúscula.")
    if REQUIRE_SPECIAL and not SPECIAL_RE.search(pwd):
        errors.append("A senha deve conter pelo menos 1 caractere especial (p. ex. !@#).")

    # Senhas comuns
    if FORBID_COMMON and pwd.lower() in COMMON_PASSWORDS:
        errors.append("A senha escolhida é muito comum. Escolha outra.")

    # Não conter identificadores do usuário (email/cpf/nome)
    if BLOCK_IDENTIFIERS and identifiers:
        if _contains_identifier(pwd, identifiers):
            errors.append("A senha não deve conter informações pessoais (e-mail/CPF/nome).")

    return errors


def compare_new_password_and_confirm(new_password: str, new_password_confirm: str) -> Optional[str]:
    """
    Compara a confirmação da senha.
    Retorna None se ok, ou a mensagem de erro (string) se divergir.
    """
    if (new_password or "") != (new_password_confirm or ""):
        return "A confirmação da senha não confere."
    return None


def enforce_password_policy(new_password: str, *, identifiers: Optional[Iterable[Optional[str]]] = None) -> None:
    """
    Dispara ValueError com a primeira mensagem, caso a senha viole a política.
    Útil quando se deseja falhar rápido. Para coletar todas, use evaluate_password().
    """
    errs = evaluate_password(new_password, identifiers=identifiers)
    if errs:
        raise ValueError(errs[0])


def summarize_policy() -> dict:
    """
    Retorna um dicionário com as regras ativas da política (útil para /schema/UI).
    """
    return {
        "min_length": MIN_LENGTH,
        "require_digit": REQUIRE_DIGIT,
        "require_letter": REQUIRE_LETTER,
        "require_upper": REQUIRE_UPPER,
        "require_lower": REQUIRE_LOWER,
        "require_special": REQUIRE_SPECIAL,
        "disallow_whitespace": DISALLOW_WHITESPACE,
        "forbid_common": FORBID_COMMON,
        "block_identifiers": BLOCK_IDENTIFIERS,
        "min_diff_chars": MIN_DIFF_CHARS,
    }
