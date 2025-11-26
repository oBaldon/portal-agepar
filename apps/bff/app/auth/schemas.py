from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ---------------------------------------------------------------------------
# Esquemas Pydantic (v2) para o módulo de Autenticação / Sessões
# - Mantém compatibilidade com o contrato atual (LoginOut "flat")
# - Prepara também modelos aninhados (LoginResponse: { user, session })
# - Usa ConfigDict(populate_by_name=True, extra="ignore") para evitar 422 triviais
# ---------------------------------------------------------------------------

CPF_RE = re.compile(r"^\d{11}$")


# ---------------------------- Register ----------------------------

class RegisterIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = Field(min_length=2)
    email: Optional[EmailStr] = None
    cpf: Optional[str] = Field(default=None, description="CPF com 11 dígitos numéricos")
    password: str = Field(min_length=8, max_length=128)

    def validate_business(self):
        if not self.email and not self.cpf:
            raise ValueError("Informe email ou CPF.")
        if self.cpf and not CPF_RE.fullmatch(self.cpf):
            raise ValueError("CPF deve ter exatamente 11 dígitos numéricos.")


class RegisterOut(BaseModel):
    id: uuid.UUID
    name: str
    email: Optional[str] = None
    cpf: Optional[str] = None
    status: str


# ---------------------------- Login (input) ----------------------------

class LoginIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    identifier: str = Field(description="e-mail ou CPF (11 dígitos)")
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = False


# ---------------------------- Login (output - formatos) ----------------------------

class LoginUser(BaseModel):
    cpf: Optional[str] = None
    nome: str
    email: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    unidades: List[str] = Field(default_factory=list)
    auth_mode: str
    is_superuser: bool = False
    must_change_password: bool = False


class LoginSession(BaseModel):
    id: uuid.UUID
    expires_at: datetime


class LoginOut(LoginUser):
    """
    Formato compatível com o contrato atual do /api/auth/login (flat).
    """
    pass


class LoginResponse(BaseModel):
    """
    Formato alternativo (aninhado), caso desejemos retornar:
    {
      "user": { ...LoginUser... },
      "session": { "id": "...", "expires_at": "..." }
    }
    """
    user: LoginUser
    session: LoginSession
