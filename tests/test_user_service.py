"""Testes do CRUD de usuários, contra o banco de configuração local (SQLite temporário)."""

import pytest

from app.db.session import DatabaseSessionFactory
from app.models.user import UserRole
from app.services.auth_service import AuthService
from app.services.user_service import DuplicateUsernameError, UserService


def _make_service(session_factory: DatabaseSessionFactory) -> UserService:
    return UserService(session_factory, AuthService(session_factory))


def test_create_and_get_by_username(session_factory: DatabaseSessionFactory) -> None:
    """Um usuário criado deve poder ser recuperado pelo nome, com os campos corretos."""
    service = _make_service(session_factory)

    service.create(username="joao", plain_password="senha123", role=UserRole.USER)

    user = service.get_by_username("joao")
    assert user is not None
    assert user.role == UserRole.USER
    assert user.active is True


def test_create_with_duplicate_username_raises(session_factory: DatabaseSessionFactory) -> None:
    """Criar um usuário com um nome já cadastrado deve levantar `DuplicateUsernameError`."""
    service = _make_service(session_factory)
    service.create(username="joao", plain_password="senha123", role=UserRole.USER)

    with pytest.raises(DuplicateUsernameError):
        service.create(username="joao", plain_password="outrasenha", role=UserRole.ADMIN)


def test_set_role_and_active(session_factory: DatabaseSessionFactory) -> None:
    """Alterar papel e ativação de um usuário deve refletir ao buscar novamente."""
    service = _make_service(session_factory)
    user = service.create(username="joao", plain_password="senha123", role=UserRole.USER)

    service.set_role(user.id, UserRole.ADMIN)
    service.set_active(user.id, active=False)

    updated = service.get_by_id(user.id)
    assert updated is not None
    assert updated.role == UserRole.ADMIN
    assert updated.active is False
