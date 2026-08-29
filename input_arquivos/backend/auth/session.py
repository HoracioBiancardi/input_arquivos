"""Sessão de usuário via cookie assinado, usada tanto pelas páginas quanto pela API REST."""

import secrets
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from input_arquivos.backend.config import Settings, get_settings

_DEFAULT_SESSION_SECRET = "change-me-in-production"


def _resolve_session_secret(settings: Settings) -> str:
    """Resolve a chave de assinatura do cookie de sessão a ser usada em runtime.

    Se `session_secret` continuar no valor padrão (ninguém configurou um
    valor próprio via `.env`/ambiente), essa chave é previsível e conhecida
    por qualquer um que leia o código-fonte — permitindo forjar offline um
    cookie de sessão de admin válido. Para não depender de o operador lembrar
    de trocar esse valor, gera-se uma chave aleatória forte na primeira
    execução e ela é persistida ao lado do banco local, para ser reaproveitada
    entre reinicializações.

    Args:
        settings: Configurações da aplicação.

    Returns:
        A chave a ser usada pelo serializador de cookies: o valor configurado
        explicitamente, ou uma chave aleatória gerada e persistida em disco.
    """
    if settings.session_secret != _DEFAULT_SESSION_SECRET:
        return settings.session_secret

    secret_path = Path(settings.app_config_db_path).parent / ".session_secret"
    if secret_path.exists():
        return secret_path.read_text(encoding="utf-8").strip()

    secret_path.parent.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_hex(32)
    secret_path.write_text(generated, encoding="utf-8")
    secret_path.chmod(0o600)
    return generated


@dataclass
class SessionUser:
    """Dados do usuário autenticado guardados no cookie de sessão.

    Attributes:
        user_id: Identificador do usuário autenticado.
        username: Nome do usuário autenticado.
        role: Papel do usuário ("admin" ou "user").
        must_change_password: Se a conta ainda está com a senha padrão do
            bootstrap e deveria trocá-la.
    """

    user_id: int
    username: str
    role: str
    must_change_password: bool = False


class SessionCookie:
    """Emite, lê e limpa o cookie de sessão assinado que identifica o usuário autenticado."""

    COOKIE_NAME = "session"
    _SALT = "session-cookie"

    def __init__(self) -> None:
        """Inicializa o serializador de cookies a partir das configurações da aplicação."""
        settings = get_settings()
        self._serializer = URLSafeTimedSerializer(_resolve_session_secret(settings), salt=self._SALT)
        self._max_age = settings.session_max_age_seconds
        self._cookie_secure = settings.session_cookie_secure

    def issue(self, response: Response, user: SessionUser) -> None:
        """Assina e grava o cookie de sessão na resposta HTTP.

        Args:
            response: Resposta HTTP onde o cookie será definido.
            user: Dados do usuário autenticado a guardar na sessão.
        """
        token = self._serializer.dumps(
            {"user_id": user.user_id, "username": user.username, "role": user.role}
        )
        response.set_cookie(
            self.COOKIE_NAME,
            token,
            max_age=self._max_age,
            httponly=True,
            samesite="strict",
            path="/",
            secure=self._cookie_secure,
        )

    def read(self, request: Request) -> SessionUser | None:
        """Lê e valida o cookie de sessão da requisição atual.

        Args:
            request: Requisição HTTP recebida.

        Returns:
            O usuário autenticado, ou `None` se não houver cookie válido
            (ausente, corrompido ou expirado).
        """
        token = request.cookies.get(self.COOKIE_NAME)
        if token is None:
            return None
        try:
            payload = self._serializer.loads(token, max_age=self._max_age)
        except (BadSignature, SignatureExpired):
            return None
        return SessionUser(user_id=payload["user_id"], username=payload["username"], role=payload["role"])

    def clear(self, response: Response) -> None:
        """Remove o cookie de sessão da resposta HTTP.

        Args:
            response: Resposta HTTP onde o cookie será removido.
        """
        response.delete_cookie(self.COOKIE_NAME, path="/")
