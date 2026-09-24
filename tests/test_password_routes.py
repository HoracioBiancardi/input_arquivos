"""Testes HTTP da troca de senha: `/api/auth/change-password` e senha definida pelo admin.

Reaproveita a fixture de `test_system_routes.py` (SQLite temporário + admin de bootstrap).
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_CONFIG_DB_PATH", str(tmp_path / "test_password_app_config.db"))

    from input_arquivos.backend import config as config_module
    from input_arquivos.backend.db import session as session_module
    from input_arquivos.backend.security import secret_box
    from input_arquivos.backend.services import container as container_module

    config_module.get_settings.cache_clear()
    session_module._factory = None
    container_module._container = None
    secret_box.reset_for_testing()

    import input_arquivos.main as main_module
    importlib.reload(main_module)

    with TestClient(main_module.app) as test_client:
        yield test_client

    config_module.get_settings.cache_clear()
    session_module._factory = None
    container_module._container = None
    secret_box.reset_for_testing()


def _login_as_admin(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200




def _create_user(client: TestClient, username: str = "maria", password: str = "Inicial-123") -> int:
    """Cria um usuário comum como admin e retorna o id."""
    _login_as_admin(client)
    response = client.post("/api/users", json={"username": username, "password": password, "role": "user"})
    assert response.status_code == 200
    client.post("/api/auth/logout")
    return response.json()["id"]


def _change(client: TestClient, current: str, new: str, username: str = "maria"):
    return client.post(
        "/api/auth/change-password",
        json={"username": username, "current_password": current, "new_password": new},
    )


def test_user_created_by_admin_must_change_password(client: TestClient) -> None:
    """Senha inicial definida pelo admin marca a conta para troca no primeiro acesso."""
    _create_user(client)

    login = client.post("/api/auth/login", json={"username": "maria", "password": "Inicial-123"})

    assert login.json()["must_change_password"] is True


def test_change_password_without_session_and_clears_flag(client: TestClient) -> None:
    """Da tela de login, sem sessão: com a senha atual certa, troca e zera a marca."""
    _create_user(client)

    response = _change(client, "Inicial-123", "Nova-senha-456")

    assert response.status_code == 204
    assert client.post("/api/auth/login", json={"username": "maria", "password": "Inicial-123"}).status_code == 401
    login = client.post("/api/auth/login", json={"username": "maria", "password": "Nova-senha-456"})
    assert login.status_code == 200
    assert login.json()["must_change_password"] is False


def test_wrong_current_password_is_401_like_login(client: TestClient) -> None:
    """Senha atual errada devolve 401 (mesmo status do login) e não troca nada."""
    _create_user(client)

    response = _change(client, "errada-000", "Nova-senha-456")

    assert response.status_code == 401
    assert client.post("/api/auth/login", json={"username": "maria", "password": "Inicial-123"}).status_code == 200


def test_unknown_user_gets_same_401_as_wrong_password(client: TestClient) -> None:
    """Usuário inexistente e senha errada respondem igual — não dá para enumerar usernames."""
    _create_user(client)

    unknown = _change(client, "qualquer-000", "Nova-senha-456", username="nao_existe")
    wrong = _change(client, "errada-000", "Nova-senha-456")

    assert (unknown.status_code, unknown.json()) == (wrong.status_code, wrong.json())


def test_change_password_counts_toward_lockout(client: TestClient) -> None:
    """Tentativas erradas na troca de senha bloqueiam a conta, como no login — sem atalho para força bruta."""
    _create_user(client)
    for _ in range(5):
        _change(client, "errada-000", "Nova-senha-456")

    response = _change(client, "Inicial-123", "Nova-senha-456")

    assert response.status_code == 401
    assert "bloqueada" in response.json()["detail"]


def test_new_password_equal_to_current_is_rejected(client: TestClient) -> None:
    """Trocar pela mesma senha não conta como troca."""
    _create_user(client)

    response = _change(client, "Inicial-123", "Inicial-123")

    assert response.status_code == 422


def test_short_new_password_is_rejected(client: TestClient) -> None:
    """Senha nova abaixo do mínimo é recusada antes de tocar no banco."""
    _create_user(client)

    assert _change(client, "Inicial-123", "curta").status_code == 422


def test_admin_reset_of_other_user_marks_must_change(client: TestClient) -> None:
    """Admin redefinindo a senha de outra pessoa marca a conta para troca."""
    user_id = _create_user(client)
    _change(client, "Inicial-123", "Nova-senha-456")
    _login_as_admin(client)

    client.patch(f"/api/users/{user_id}", json={"new_password": "Redefinida-789"})
    client.post("/api/auth/logout")

    login = client.post("/api/auth/login", json={"username": "maria", "password": "Redefinida-789"})
    assert login.json()["must_change_password"] is True
