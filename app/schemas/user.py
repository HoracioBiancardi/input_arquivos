"""Schemas Pydantic para as rotas de CRUD de usuários e controle de acesso a contexts."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.user import UserRole

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_MIN_PASSWORD_LENGTH = 8


class UserCreateRequest(BaseModel):
    """Corpo da requisição de criação de um novo usuário.

    Attributes:
        username: Nome de usuário único.
        password: Senha em texto puro (será convertida em hash bcrypt).
        role: Papel do usuário (admin ou comum).
    """

    username: str
    password: str
    role: UserRole = UserRole.USER

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        """Garante que o nome de usuário use apenas letras, números, ponto, hífen e underscore."""
        if not _USERNAME_PATTERN.match(value):
            raise ValueError("Usuário deve conter apenas letras, números, '.', '_' ou '-'.")
        return value

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        """Garante que a senha tenha o tamanho mínimo exigido."""
        if len(value) < _MIN_PASSWORD_LENGTH:
            raise ValueError(f"Senha deve ter ao menos {_MIN_PASSWORD_LENGTH} caracteres.")
        return value


class UserUpdateRequest(BaseModel):
    """Corpo da requisição de atualização de um usuário existente.

    Todos os campos são opcionais: apenas os informados são alterados.

    Attributes:
        role: Novo papel do usuário, se for o caso.
        active: Novo estado de ativação, se for o caso.
        new_password: Nova senha em texto puro, se o usuário quiser trocá-la.
    """

    role: UserRole | None = None
    active: bool | None = None
    new_password: str | None = None

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, value: str | None) -> str | None:
        """Garante que a nova senha, quando informada, tenha o tamanho mínimo exigido."""
        if value and len(value) < _MIN_PASSWORD_LENGTH:
            raise ValueError(f"Senha deve ter ao menos {_MIN_PASSWORD_LENGTH} caracteres.")
        return value


class UserContextsRequest(BaseModel):
    """Corpo da requisição para substituir os contexts liberados para um usuário.

    Attributes:
        context_ids: Ids dos contexts que o usuário deve poder acessar.
    """

    context_ids: list[int]


class UserResponse(BaseModel):
    """Representação de um usuário retornada pela API.

    Attributes:
        id: Identificador interno do usuário.
        username: Nome de usuário.
        role: Papel do usuário.
        active: Se a conta pode ser usada para login.
        last_context_name: Último context usado pelo usuário na tela de upload.
        created_at: Data de criação da conta.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: UserRole
    active: bool
    last_context_name: str | None
    created_at: datetime


class UserDetailResponse(UserResponse):
    """Representação detalhada de um usuário, incluindo os contexts liberados para ele.

    Attributes:
        context_ids: Ids dos contexts explicitamente liberados para este usuário.
    """

    context_ids: list[int] = []
