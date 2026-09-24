"""Testes HTTP (TestClient) para /api/settings/database: conexão do SQL Server de destino.

Reaproveita a fixture de `test_system_routes.py` (SQLite temporário + admin de
bootstrap) para exercitar as rotas com sessão real, incluindo o `require_admin`.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_CONFIG_DB_PATH", str(tmp_path / "test_settings_app_config.db"))

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



_VALID_PAYLOAD = {"host": "sql.interno", "port": 1433, "database": "dw", "username": "carga", "password": "S3nh@/x"}


def test_database_settings_require_admin_session(client: TestClient) -> None:
    """Sem login, nenhuma rota da conexão do banco responde (nem leitura, nem teste de conexão)."""
    assert client.get("/api/settings/database").status_code == 401
    assert client.post("/api/settings/database/test", json=_VALID_PAYLOAD).status_code == 401


def test_saved_password_is_never_returned(client: TestClient) -> None:
    """PUT e GET devolvem os campos da conexão, mas nunca a senha."""
    _login_as_admin(client)

    saved = client.put("/api/settings/database", json=_VALID_PAYLOAD)
    fetched = client.get("/api/settings/database")

    assert saved.status_code == 200
    assert fetched.json() == {
        "configured": True,
        "host": "sql.interno",
        "port": 1433,
        "database": "dw",
        "username": "carga",
        "password_configured": True,
    }
    assert "S3nh" not in saved.text + fetched.text


@pytest.mark.parametrize("host", ["mssql+pymssql://sql.interno", "sql.interno:1433", "sql.interno/dw", " "])
def test_host_with_scheme_port_or_path_is_rejected(client: TestClient, host: str) -> None:
    """O campo servidor só aceita hostname/IP — nada de URL montada à mão."""
    _login_as_admin(client)

    response = client.put("/api/settings/database", json={**_VALID_PAYLOAD, "host": host})

    assert response.status_code == 422


def test_connection_test_reports_unreachable_server(client: TestClient) -> None:
    """Servidor fora do ar vira `success=False` com mensagem, não erro 500."""
    _login_as_admin(client)

    response = client.post("/api/settings/database/test", json={**_VALID_PAYLOAD, "host": "127.0.0.1", "port": 1})

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "Falha ao conectar" in response.json()["message"]
