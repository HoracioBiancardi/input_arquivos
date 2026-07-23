"""Sessão de usuário via cookie assinado, usada tanto pelas páginas quanto pela API REST."""

from dataclasses import dataclass

from fastapi import Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings


@dataclass
class SessionUser:
    """Dados do usuário autenticado guardados no cookie de sessão.

    Attributes:
        user_id: Identificador do usuário autenticado.
        username: Nome do usuário autenticado.
        role: Papel do usuário ("admin" ou "user").
    """

    user_id: int
    username: str
    role: str


class SessionCookie:
    """Emite, lê e limpa o cookie de sessão assinado que identifica o usuário autenticado."""

    COOKIE_NAME = "session"
    _SALT = "session-cookie"

    def __init__(self) -> None:
        """Inicializa o serializador de cookies a partir das configurações da aplicação."""
        settings = get_settings()
        self._serializer = URLSafeTimedSerializer(settings.session_secret, salt=self._SALT)
        self._max_age = settings.session_max_age_seconds

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
            samesite="lax",
            path="/",
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
