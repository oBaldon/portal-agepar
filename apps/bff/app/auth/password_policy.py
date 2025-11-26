# apps/bff/app/auth/password_policy.py
"""
Política de Senhas do BFF do Portal AGEPAR.

Objetivo
--------
Validar novas senhas de forma padronizada e configurável via variáveis de
ambiente, retornando mensagens de erro legíveis (pt-BR) para exibição no
frontend.

Uso rápido
----------
from .password_policy import evaluate_password, enforce_password_policy

errors = evaluate_password(new_password, identifiers=[email, cpf, nome])
if errors:
    # Ex.: lançar HTTP 422 com os erros para o cliente
    ...

# Falhar rápido (primeiro erro):
enforce_password_policy(new_password, identifiers=[email, cpf])

Variáveis de ambiente
---------------------
- AUTH_PASSWORD_POLICY_MIN_LENGTH           (int, default=8)
- AUTH_PASSWORD_POLICY_REQUIRE_DIGIT        (bool, default=true)
- AUTH_PASSWORD_POLICY_REQUIRE_LETTER       (bool, default=true)
- AUTH_PASSWORD_POLICY_REQUIRE_UPPER        (bool, default=false)
- AUTH_PASSWORD_POLICY_REQUIRE_LOWER        (bool, default=false)
- AUTH_PASSWORD_POLICY_REQUIRE_SPECIAL      (bool, default=false)
- AUTH_PASSWORD_POLICY_DISALLOW_WHITESPACE  (bool, default=true)
- AUTH_PASSWORD_POLICY_FORBID_COMMON        (bool, default=true)
- AUTH_PASSWORD_POLICY_BLOCK_IDENTIFIERS    (bool, default=true)  # bloqueia e-mail/CPF/nome na senha
- AUTH_PASSWORD_POLICY_MIN_DIFF_CHARS       (int, default=4)      # diversidade mínima de caracteres distintos
"""

from __future__ import annotations

import os
import re
from typing import Iterable, List, Optional

def _env_bool(name: str, default: bool) -> bool:
    """
    Converte uma variável de ambiente em booleano.

    Parâmetros
    ----------
    name : str
        Nome da variável de ambiente.
    default : bool
        Valor padrão caso a variável não exista.

    Retorna
    -------
    bool
        True para valores como "1", "true", "yes", "y", "on" (case-insensitive).
    """
    val = os.getenv(name)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "y", "on")


def _env_int(name: str, default: int) -> int:
    """
    Converte uma variável de ambiente em inteiro, com fallback.

    Parâmetros
    ----------
    name : str
        Nome da variável de ambiente.
    default : int
        Valor padrão caso a conversão falhe.

    Retorna
    -------
    int
        Valor convertido ou o padrão informado.
    """
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


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

SPECIAL_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
DIGIT_RE = re.compile(r"\d")
LETTER_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ]")
UPPER_RE = re.compile(r"[A-ZÁÉÍÓÚÂÊÎÔÛÀÈÌÒÙÃÕÇ]")
LOWER_RE = re.compile(r"[a-záéíóúâêîôûàèìòùãõç]")

CPF_ONLY_DIGITS_RE = re.compile(r"^\d{11}$")

COMMON_PASSWORDS = {
    "123456", "12345678", "123456789", "senha", "password", "qwerty", "abc123",
    "111111", "123123", "000000", "iloveyou", "admin",
}


def _normalize_identifier(s: Optional[str]) -> Optional[str]:
    """
    Normaliza um identificador de usuário (e-mail/CPF/nome) para comparação.

    - Faz strip + lower.
    - Remove separadores visuais comuns (.,-_/() e espaços).

    Parâmetros
    ----------
    s : Optional[str]
        Valor bruto do identificador.

    Retorna
    -------
    Optional[str]
        Identificador normalizado, ou None se vazio.
    """
    if not s:
        return None
    s = s.strip().lower()
    s = re.sub(r"[.\-_/()\s]", "", s)
    return s or None


def _contains_identifier(pwd: str, identifiers: Iterable[Optional[str]]) -> bool:
    """
    Verifica se a senha contém algum identificador do usuário.

    Regras
    ------
    - Substrings com >= 3 caracteres do identificador normalizado invalidam.
    - Para CPF (11 dígitos), bloqueia se o número aparecer integralmente.

    Parâmetros
    ----------
    pwd : str
        Nova senha.
    identifiers : Iterable[Optional[str]]
        Coleção de identificadores (e-mail/CPF/nome), podendo conter None.

    Retorna
    -------
    bool
        True se algum identificador for encontrado na senha.
    """
    pwd_l = pwd.lower()
    for raw in identifiers or []:
        ident = _normalize_identifier(raw)
        if not ident:
            continue
        if ident and len(ident) >= 3 and ident in pwd_l:
            return True
        if CPF_ONLY_DIGITS_RE.fullmatch(ident) and ident in pwd_l:
            return True
    return False


def evaluate_password(new_password: str, *, identifiers: Optional[Iterable[Optional[str]]] = None) -> List[str]:
    """
    Avalia a senha conforme a política ativa e retorna todas as violações.

    Parâmetros
    ----------
    new_password : str
        Senha proposta.
    identifiers : Optional[Iterable[Optional[str]]]
        Identificadores do usuário para checagem de conteúdo (e-mail/CPF/nome).

    Retorna
    -------
    List[str]
        Lista de mensagens de erro. Vazia indica aprovação na política.

    Validações aplicadas
    --------------------
    - Tamanho mínimo (MIN_LENGTH).
    - Espaços em branco (DISALLOW_WHITESPACE).
    - Diversidade mínima de caracteres distintos (MIN_DIFF_CHARS).
    - Presença de dígito/letra/maiúscula/minúscula/especial conforme flags.
    - Bloqueio de senhas comuns (FORBID_COMMON).
    - Bloqueio de conteúdo que contenha identificadores (BLOCK_IDENTIFIERS).
    """
    errors: List[str] = []
    pwd = new_password or ""

    if len(pwd) < MIN_LENGTH:
        errors.append(f"A senha deve ter pelo menos {MIN_LENGTH} caracteres.")

    if DISALLOW_WHITESPACE and any(ch.isspace() for ch in pwd):
        errors.append("A senha não pode conter espaços em branco.")

    if MIN_DIFF_CHARS > 0 and len(set(pwd)) < MIN_DIFF_CHARS:
        errors.append(f"A senha deve possuir ao menos {MIN_DIFF_CHARS} caracteres distintos.")

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

    if FORBID_COMMON and pwd.lower() in COMMON_PASSWORDS:
        errors.append("A senha escolhida é muito comum. Escolha outra.")

    if BLOCK_IDENTIFIERS and identifiers:
        if _contains_identifier(pwd, identifiers):
            errors.append("A senha não deve conter informações pessoais (e-mail/CPF/nome).")

    return errors


def compare_new_password_and_confirm(new_password: str, new_password_confirm: str) -> Optional[str]:
    """
    Compara senha e confirmação.

    Parâmetros
    ----------
    new_password : str
        Senha proposta.
    new_password_confirm : str
        Confirmação informada.

    Retorna
    -------
    Optional[str]
        None se iguais; mensagem de erro caso divergentes.
    """
    if (new_password or "") != (new_password_confirm or ""):
        return "A confirmação da senha não confere."
    return None


def enforce_password_policy(new_password: str, *, identifiers: Optional[Iterable[Optional[str]]] = None) -> None:
    """
    Aplica a política e lança a primeira violação encontrada.

    Parâmetros
    ----------
    new_password : str
        Senha proposta.
    identifiers : Optional[Iterable[Optional[str]]]
        Identificadores do usuário para checagem de conteúdo.

    Levanta
    -------
    ValueError
        Quando a senha viola alguma regra (primeiro erro da lista).

    Observações
    -----------
    Use `evaluate_password` quando quiser retornar **todas** as violações
    para o cliente. `enforce_password_policy` é útil para fluxos de falha rápida.
    """
    errs = evaluate_password(new_password, identifiers=identifiers)
    if errs:
        raise ValueError(errs[0])


def summarize_policy() -> dict:
    """
    Expõe as regras ativas da política em um dicionário.

    Retorna
    -------
    dict
        Estrutura contendo os flags e parâmetros efetivos (min_length etc.).
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
