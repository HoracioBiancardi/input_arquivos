"""Serviço de autenticação: hashing de senha e validação de credenciais de login."""

from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy import select

from app.config import get_settings
from app.db.session import DatabaseSessionFactory
from app.models.user import User


class AccountLockedError(ValueError):
    """Erro levantado ao tentar autenticar uma conta temporariamente bloqueada por tentativas erradas.

    Attributes:
        retry_after_seconds: Quantos segundos faltam até a conta ser desbloqueada.
    """

    def __init__(self, retry_after_seconds: int) -> None:
        """Inicializa o erro com o tempo restante de bloqueio.

        Args:
            retry_after_seconds: Quantos segundos faltam até a conta ser desbloqueada.
        """
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Conta bloqueada temporariamente. Tente novamente em {retry_after_seconds} segundos.")


def _as_aware_utc(value: datetime) -> datetime:
    """Garante que um `datetime` lido do banco tenha timezone UTC explícito.

    SQLite não preserva timezone: um `datetime` gravado como aware pode
    voltar naive após o round-trip. Trata esse valor como UTC nesse caso.

    Args:
        value: Datetime lido do banco, aware ou naive.

    Returns:
        O mesmo instante, com `tzinfo` UTC garantido.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


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

        Cada senha incorreta soma uma tentativa falha; ao atingir o limite
        configurado (`Settings.max_failed_login_attempts`), a conta fica
        temporariamente bloqueada (`Settings.lockout_duration_seconds`),
        mesmo que a senha correta seja informada depois. Um login bem-sucedido
        zera o contador.

        Args:
            username: Nome de usuário informado no login.
            plain_password: Senha em texto puro informada no login.

        Returns:
            Instância de `User` se as credenciais forem válidas e a conta estiver
            ativa, ou `None` se usuário/senha forem inválidos.

        Raises:
            AccountLockedError: Se a conta estiver temporariamente bloqueada
                por excesso de tentativas erradas.
        """
        settings = get_settings()
        now = datetime.now(timezone.utc)

        with self._session_factory.session() as db_session:
            user = db_session.execute(
                select(User).where(User.username == username, User.active.is_(True))
            ).scalar_one_or_none()
            if user is None:
                return None

            if user.locked_until is not None and _as_aware_utc(user.locked_until) > now:
                retry_after = int((_as_aware_utc(user.locked_until) - now).total_seconds())
                raise AccountLockedError(retry_after)

            if not self._crypt_context.verify(plain_password, user.password_hash):
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= settings.max_failed_login_attempts:
                    user.locked_until = now + timedelta(seconds=settings.lockout_duration_seconds)
                return None

            user.failed_login_attempts = 0
            user.locked_until = None
            return user
