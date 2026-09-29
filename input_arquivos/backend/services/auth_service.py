"""Serviço de autenticação: hashing de senha e validação de credenciais de login."""

import secrets
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from sqlalchemy import select, update

from input_arquivos.backend.config import get_settings
from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.models.user import User


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
        # Hash de uma senha aleatória, conferido quando o usuário não existe ou está
        # bloqueado, para o tempo de resposta não depender de o usuário existir.
        self._dummy_hash = self._crypt_context.hash(secrets.token_urlsafe(16))

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
        zera o contador, e o fim do bloqueio também (novas N tentativas).

        A tentativa é **reservada no banco antes** de conferir a senha (incremento
        atômico). Se a checagem viesse antes e a contagem depois do bcrypt, uma
        rajada de requisições em paralelo passaria toda pela checagem e testaria
        dezenas de senhas antes do bloqueio (CWE-362). Com a reserva, no máximo
        `max_failed_login_attempts` senhas são conferidas por janela de bloqueio.

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
        max_attempts = settings.max_failed_login_attempts
        now = datetime.now(timezone.utc)

        # Transações curtas: o bcrypt (~200 ms) roda fora delas, para a escrita no
        # SQLite não travar os logins de todo mundo enquanto o hash é calculado.
        with self._session_factory.session() as db_session:
            user = db_session.execute(
                select(User).where(User.username == username, User.active.is_(True))
            ).scalar_one_or_none()
            if user is None:
                attempts = None
            elif user.locked_until is not None and _as_aware_utc(user.locked_until) > now:
                attempts = None
            else:
                if user.locked_until is not None:
                    # Bloqueio vencido: recomeça a contagem.
                    db_session.execute(
                        update(User).where(User.id == user.id).values(failed_login_attempts=0, locked_until=None)
                    )
                attempts = db_session.execute(
                    update(User)
                    .where(User.id == user.id)
                    .values(failed_login_attempts=User.failed_login_attempts + 1)
                    .returning(User.failed_login_attempts)
                ).scalar_one()

        if user is None or attempts is None or attempts > max_attempts:
            # Mesmo custo de um usuário existente: sem o bcrypt aqui, a resposta rápida
            # revelaria quais usernames existem ou estão bloqueados (CWE-208).
            self._crypt_context.verify(plain_password, self._dummy_hash)
            if user is None:
                return None
            if attempts is None:
                retry_after = int((_as_aware_utc(user.locked_until) - now).total_seconds())
            else:  # outra requisição em paralelo já esgotou as tentativas
                retry_after = settings.lockout_duration_seconds
            raise AccountLockedError(retry_after)

        if not self._crypt_context.verify(plain_password, user.password_hash):
            if attempts >= max_attempts:
                with self._session_factory.session() as db_session:
                    db_session.execute(
                        update(User)
                        .where(User.id == user.id)
                        .values(locked_until=now + timedelta(seconds=settings.lockout_duration_seconds))
                    )
            return None

        with self._session_factory.session() as db_session:
            db_session.execute(update(User).where(User.id == user.id).values(failed_login_attempts=0, locked_until=None))
        user.failed_login_attempts = 0
        user.locked_until = None
        return user
