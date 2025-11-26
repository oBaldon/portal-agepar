# apps/bff/app/auth/schemas.py
"""
Esquemas (Pydantic v2) do módulo de autenticação e sessões do BFF do Portal AGEPAR.

Visão geral
-----------
Este módulo define modelos de entrada e saída utilizados nas rotas de autenticação:
- Registro de usuários locais.
- Login e sessão.
- Respostas compatíveis com o contrato atual (formato "flat") e um formato alternativo
  com dados aninhados (usuário + sessão).

Decisões de projeto
-------------------
- Pydantic v2 com `ConfigDict(populate_by_name=True, extra="ignore")` nos modelos
  de entrada, reduzindo erros 422 por campos extras e aceitando nomes alternativos.
- `LoginOut` estende `LoginUser` para manter compatibilidade com o contrato atual.
- `LoginResponse` opcional e mais expressivo, caso seja necessário evoluir o contrato
  para um formato estruturado com enclausuramento de `user` e `session`.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

CPF_RE = re.compile(r"^\d{11}$")


class RegisterIn(BaseModel):
    """
    Entrada para registro de usuário local.

    Campos
    ------
    name : str
        Nome do usuário (mínimo de 2 caracteres).
    email : Optional[EmailStr]
        E-mail válido; obrigatório se `cpf` não for informado.
    cpf : Optional[str]
        CPF com exatamente 11 dígitos numéricos; obrigatório se `email` não for informado.
    password : str
        Senha inicial do usuário (mínimo de 8, máximo de 128 caracteres).

    Observações
    -----------
    - A validação de negócio adicional é feita por `validate_business()`:
      exige ao menos um entre `email` e `cpf` e valida padrão do CPF.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    name: str = Field(min_length=2)
    email: Optional[EmailStr] = None
    cpf: Optional[str] = Field(default=None, description="CPF com 11 dígitos numéricos")
    password: str = Field(min_length=8, max_length=128)

    def validate_business(self) -> None:
        """
        Regras de negócio do cadastro:
        - Exige que ao menos um identificador (`email` ou `cpf`) seja informado.
        - Quando `cpf` for informado, valida se possui 11 dígitos numéricos.

        Levanta
        -------
        ValueError
            Quando nenhuma identificação foi informada, ou o CPF está em formato inválido.
        """
        if not self.email and not self.cpf:
            raise ValueError("Informe email ou CPF.")
        if self.cpf and not CPF_RE.fullmatch(self.cpf):
            raise ValueError("CPF deve ter exatamente 11 dígitos numéricos.")


class RegisterOut(BaseModel):
    """
    Saída do endpoint de registro de usuário.

    Campos
    ------
    id : uuid.UUID
        Identificador do usuário criado.
    name : str
        Nome do usuário.
    email : Optional[str]
        E-mail normalizado, quando informado.
    cpf : Optional[str]
        CPF normalizado, quando informado.
    status : str
        Status do usuário após criação (ex.: "active").
    """
    id: uuid.UUID
    name: str
    email: Optional[str] = None
    cpf: Optional[str] = None
    status: str


class LoginIn(BaseModel):
    """
    Entrada para autenticação local.

    Campos
    ------
    identifier : str
        E-mail ou CPF (11 dígitos).
    password : str
        Senha do usuário.
    remember_me : bool
        Quando verdadeiro, usa TTL de sessão estendido.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    identifier: str = Field(description="e-mail ou CPF (11 dígitos)")
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = False


class LoginUser(BaseModel):
    """
    Estrutura do usuário autenticado retornada ao frontend.

    Campos
    ------
    cpf : Optional[str]
        CPF do usuário, quando disponível.
    nome : str
        Nome do usuário (campo legado, mantido para compatibilidade).
    email : Optional[str]
        E-mail do usuário, quando disponível.
    roles : List[str]
        Lista de papéis (RBAC) efetivos do usuário.
    unidades : List[str]
        Unidades/órgãos vinculados ao usuário (se aplicável).
    auth_mode : str
        Origem da autenticação (ex.: "local").
    is_superuser : bool
        Sinalizador de superusuário (bypass de RBAC em algumas regras).
    must_change_password : bool
        Indica se o usuário precisa trocar a senha antes de acessar áreas protegidas.
    """
    cpf: Optional[str] = None
    nome: str
    email: Optional[str] = None
    roles: List[str] = Field(default_factory=list)
    unidades: List[str] = Field(default_factory=list)
    auth_mode: str
    is_superuser: bool = False
    must_change_password: bool = False


class LoginSession(BaseModel):
    """
    Metadados mínimos da sessão autenticada.

    Campos
    ------
    id : uuid.UUID
        Identificador da sessão persistida.
    expires_at : datetime
        Data/hora de expiração da sessão.
    """
    id: uuid.UUID
    expires_at: datetime


class LoginOut(LoginUser):
    """
    Saída compatível com o contrato atual de `/api/auth/login` (formato "flat").

    Notas
    -----
    - Estende `LoginUser` e é retornado diretamente no login e troca de senha.
    - Mantém nomes de campos legados esperados pelo frontend.
    """
    pass


class LoginResponse(BaseModel):
    """
    Saída alternativa com dados aninhados (usuário + sessão).

    Exemplo
    -------
    {
      "user": { ...LoginUser... },
      "session": { "id": "...", "expires_at": "..." }
    }

    Campos
    ------
    user : LoginUser
        Estrutura com dados do usuário autenticado.
    session : LoginSession
        Estrutura com dados da sessão criada.
    """
    user: LoginUser
    session: LoginSession
