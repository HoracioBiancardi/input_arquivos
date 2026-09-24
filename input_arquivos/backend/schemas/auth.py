"""Schemas Pydantic para as rotas de autenticação."""

from pydantic import BaseModel, field_validator

from input_arquivos.backend.schemas.user import MIN_PASSWORD_LENGTH


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
        must_change_password: Se a conta ainda está com a senha padrão do
            bootstrap e deveria trocá-la.
    """

    username: str
    role: str
    must_change_password: bool = False


class ChangePasswordRequest(BaseModel):
    """Corpo da requisição de troca da própria senha (tela de login ou "Minha senha").

    Não exige sessão: quem sabe a senha atual pode trocá-la, inclusive antes
    de entrar. A senha atual passa pelo mesmo controle de tentativas do login.

    Attributes:
        username: Nome de usuário.
        current_password: Senha atual.
        new_password: Senha nova (mínimo `MIN_PASSWORD_LENGTH` caracteres).
    """

    username: str
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, value: str) -> str:
        """Garante que a senha nova tenha o tamanho mínimo exigido."""
        if len(value) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"Senha deve ter ao menos {MIN_PASSWORD_LENGTH} caracteres.")
        return value
