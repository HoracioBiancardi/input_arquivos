"""Testes HTTP (TestClient) para /api/system/*.

Primeiro teste HTTP-level do projeto — os demais 84 testes existentes são
unitários (services/schemas/readers/writers chamados diretamente). `app` é
construído uma única vez no import de `input_arquivos.main` (sem lifespan),
rodando `DatabaseBootstrapper` contra o banco real de `settings.app_config_db_path`
— por isso a fixture abaixo aponta `APP_CONFIG_DB_PATH` para um SQLite
temporário e recarrega o módulo antes de importar `app`, garantindo que os
testes não leiam/escrevam no banco de desenvolvimento real e tenham um admin
previsível (`admin`/`admin123`, os defaults de bootstrap) para autenticar
contra as rotas protegidas por `require_admin`.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_CONFIG_DB_PATH", str(tmp_path / "test_system_app_config.db"))

    from input_arquivos.backend import config as config_module
    from input_arquivos.backend.db import session as session_module
    from input_arquivos.backend.services import container as container_module

    config_module.get_settings.cache_clear()
    session_module._factory = None
    container_module._container = None

    import input_arquivos.main as main_module
    importlib.reload(main_module)

    with TestClient(main_module.app) as test_client:
        yield test_client

    config_module.get_settings.cache_clear()
    session_module._factory = None
    container_module._container = None


def _login_as_admin(client: TestClient) -> None:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200


def test_system_health_requires_admin_session(client: TestClient):
    response = client.get("/api/system/health")
    assert response.status_code == 401

    _login_as_admin(client)
    response = client.get("/api/system/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "uptime_seconds" in data


def test_system_metrics(client: TestClient):
    _login_as_admin(client)
    response = client.get("/api/system/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "uptime_seconds" in data
    assert data["total_users"] == 1
    assert data["total_contexts"] == 0
