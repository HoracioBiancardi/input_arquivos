"""Schemas Pydantic para as rotas de autenticação."""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Corpo da requisição de login.

    Attributes:
        username: Nome de usuário informado no login.
        password: Senha em texto puro informada no login.
    """

    username: str
    password: str


class SessionUserResponse(BaseModel):
    """Dados do usuário autenticado retornados após login ou em `/api/auth/me`.

    Attributes:
        username: Nome do usuário autenticado.
        role: Papel do usuário ("admin" ou "user").
    """

    username: str
    role: str
