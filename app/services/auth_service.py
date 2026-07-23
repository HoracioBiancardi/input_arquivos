"""Serviço de autenticação: hashing de senha e validação de credenciais de login."""

from passlib.context import CryptContext
from sqlalchemy import select

from app.db.session import DatabaseSessionFactory
from app.models.user import User


class AuthService:
    """Responsável por hashing/verificação de senha e autenticação de usuários."""

    def __init__(self, session_factory: DatabaseSessionFactory) -> None:
        """Inicializa o serviço de autenticação.

        Args:
            session_factory: Fábrica de sessões do banco de configuração local.
        """
        self._session_factory = session_factory
        self._crypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(self, plain_password: str) -> str:
        """Gera o hash bcrypt de uma senha em texto puro.

        Args:
            plain_password: Senha em texto puro.

        Returns:
            Hash bcrypt da senha.
        """
        return self._crypt_context.hash(plain_password)

    def authenticate(self, username: str, plain_password: str) -> User | None:
        """Valida usuário/senha e retorna o usuário autenticado, se as credenciais forem válidas.

        Args:
            username: Nome de usuário informado no login.
            plain_password: Senha em texto puro informada no login.

        Returns:
            Instância de `User` se as credenciais forem válidas e a conta estiver
            ativa, ou `None` caso contrário.
        """
        with self._session_factory.session() as db_session:
            user = db_session.execute(
                select(User).where(User.username == username, User.active.is_(True))
            ).scalar_one_or_none()
            if user is None:
                return None
            if not self._crypt_context.verify(plain_password, user.password_hash):
                return None
            return user
