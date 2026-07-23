"""Testes do serviço de autenticação: validação de credenciais e bloqueio por tentativas erradas."""

from datetime import datetime, timedelta, timezone

import pytest

from app.config import get_settings
from app.db.session import DatabaseSessionFactory
from app.models.user import User, UserRole
from app.services.auth_service import AccountLockedError, AuthService
from app.services.user_service import UserService


def _create_user(session_factory: DatabaseSessionFactory, auth_service: AuthService) -> User:
    user_service = UserService(session_factory, auth_service)
    return user_service.create(username="joao", plain_password="senha-correta", role=UserRole.USER)


def test_authenticate_with_correct_password_succeeds(session_factory: DatabaseSessionFactory) -> None:
    """Autenticar com usuário/senha corretos deve retornar o usuário."""
    service = AuthService(session_factory)
    _create_user(session_factory, service)

    user = service.authenticate("joao", "senha-correta")

    assert user is not None
    assert user.username == "joao"
    assert user.failed_login_attempts == 0


def test_authenticate_with_wrong_password_increments_counter(session_factory: DatabaseSessionFactory) -> None:
    """Cada senha errada deve incrementar `failed_login_attempts` sem bloquear antes do limite."""
    service = AuthService(session_factory)
    created = _create_user(session_factory, service)

    result = service.authenticate("joao", "senha-errada")

    assert result is None
    with session_factory.session() as db_session:
        user = db_session.get(User, created.id)
        assert user is not None
        assert user.failed_login_attempts == 1
        assert user.locked_until is None


def test_authenticate_locks_account_after_max_attempts(session_factory: DatabaseSessionFactory) -> None:
    """Ao atingir o limite de tentativas erradas, a conta deve ficar bloqueada mesmo com a senha certa."""
    service = AuthService(session_factory)
    _create_user(session_factory, service)
    max_attempts = get_settings().max_failed_login_attempts

    for _ in range(max_attempts):
        assert service.authenticate("joao", "senha-errada") is None

    with pytest.raises(AccountLockedError):
        service.authenticate("joao", "senha-correta")


def test_lockout_expires_after_duration(session_factory: DatabaseSessionFactory) -> None:
    """Depois que `locked_until` passa, a conta volta a autenticar normalmente e o contador zera."""
    service = AuthService(session_factory)
    created = _create_user(session_factory, service)
    max_attempts = get_settings().max_failed_login_attempts

    for _ in range(max_attempts):
        service.authenticate("joao", "senha-errada")

    with session_factory.session() as db_session:
        db_user = db_session.get(User, created.id)
        db_user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)

    user = service.authenticate("joao", "senha-correta")

    assert user is not None
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
