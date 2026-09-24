"""Testes do SystemSettingsService: configuração global do MinIO (admin, com fallback pro .env)."""

import pytest
from sqlalchemy.engine import make_url

from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.services.system_settings_service import (
    DatabaseConfigIncompleteError,
    MinioConfigIncompleteError,
    SystemSettingsService,
)


def test_get_minio_config_falls_back_to_env_when_nothing_saved(session_factory: DatabaseSessionFactory) -> None:
    """Sem configuração salva via admin, deve usar os valores do .env/config.py."""
    service = SystemSettingsService(session_factory)

    config = service.get_minio_config()

    assert config.source == "env"


def test_update_and_get_minio_config(session_factory: DatabaseSessionFactory) -> None:
    """Uma configuração salva via admin deve sobrepor o fallback do .env."""
    service = SystemSettingsService(session_factory)

    service.update_minio_config(
        endpoint="minio.interno:9000", access_key="chave-acesso", secret_key="chave-secreta", secure=True
    )

    config = service.get_minio_config()
    assert config.source == "admin"
    assert config.endpoint == "minio.interno:9000"
    assert config.access_key == "chave-acesso"
    assert config.secret_key == "chave-secreta"
    assert config.secure is True


def test_update_without_secret_key_keeps_existing_one(session_factory: DatabaseSessionFactory) -> None:
    """Editar endpoint/access_key sem informar secret_key deve manter a chave já salva."""
    service = SystemSettingsService(session_factory)
    service.update_minio_config(
        endpoint="minio.interno:9000", access_key="chave-acesso", secret_key="chave-secreta", secure=False
    )

    service.update_minio_config(endpoint="minio.novo:9000", access_key="chave-acesso", secret_key=None, secure=True)

    config = service.get_minio_config()
    assert config.endpoint == "minio.novo:9000"
    assert config.secret_key == "chave-secreta"
    assert config.secure is True


def test_update_without_secret_key_and_none_saved_raises(session_factory: DatabaseSessionFactory) -> None:
    """Salvar pela primeira vez sem secret_key deve falhar (não há chave anterior para manter)."""
    service = SystemSettingsService(session_factory)

    with pytest.raises(MinioConfigIncompleteError):
        service.update_minio_config(endpoint="minio.interno:9000", access_key="chave-acesso", secret_key=None, secure=False)


def test_clear_minio_config_reverts_to_env_fallback(session_factory: DatabaseSessionFactory) -> None:
    """Remover a configuração salva deve voltar a usar o .env como fonte."""
    service = SystemSettingsService(session_factory)
    service.update_minio_config(
        endpoint="minio.interno:9000", access_key="chave-acesso", secret_key="chave-secreta", secure=False
    )

    service.clear_minio_config()

    config = service.get_minio_config()
    assert config.source == "env"


def test_display_config_never_exposes_secret_key(session_factory: DatabaseSessionFactory) -> None:
    """A representação para a API nunca deve incluir a chave secreta em texto puro."""
    service = SystemSettingsService(session_factory)
    service.update_minio_config(
        endpoint="minio.interno:9000", access_key="chave-acesso", secret_key="chave-secreta", secure=False
    )

    display = service.get_minio_config_for_display()

    assert "secret_key" not in display
    assert display["secret_key_configured"] is True
    assert "chave-secreta" not in str(display.values())


def _save_database(service: SystemSettingsService, password: str | None = "S3nh@/forte:%") -> None:
    """Salva uma conexão de SQL Server de exemplo (senha com caracteres que quebrariam uma URL montada à mão)."""
    service.update_database_config(
        host="sql.interno", port=1433, database="dw", username="carga", password=password
    )


def test_database_url_escapes_special_characters_in_password(session_factory: DatabaseSessionFactory) -> None:
    """A URL é montada por `URL.create`, então `@`, `/`, `:` e `%` na senha não corrompem host/banco."""
    service = SystemSettingsService(session_factory)
    _save_database(service)

    url = make_url(service.get_database_url().render_as_string(hide_password=False))

    assert url.drivername == "mssql+pymssql"
    assert url.password == "S3nh@/forte:%"
    assert (url.host, url.port, url.database, url.username) == ("sql.interno", 1433, "dw", "carga")


def test_database_display_never_returns_password(session_factory: DatabaseSessionFactory) -> None:
    """A exibição traz os campos da conexão, mas só um indicador de que a senha existe."""
    service = SystemSettingsService(session_factory)
    _save_database(service)

    display = service.get_database_config_for_display()

    assert display["configured"] is True
    assert display["password_configured"] is True
    assert "S3nh" not in str(display)


def test_database_update_without_password_keeps_existing_one(session_factory: DatabaseSessionFactory) -> None:
    """Editar servidor/banco sem redigitar a senha mantém a senha salva."""
    service = SystemSettingsService(session_factory)
    _save_database(service)

    service.update_database_config(host="sql2.interno", port=14330, database="dw2", username="carga", password=None)

    config = service.get_database_config()
    assert (config.host, config.port, config.database, config.password) == ("sql2.interno", 14330, "dw2", "S3nh@/forte:%")


def test_first_database_config_requires_password(session_factory: DatabaseSessionFactory) -> None:
    """Sem senha informada nem salva, a primeira configuração é recusada."""
    with pytest.raises(DatabaseConfigIncompleteError):
        _save_database(SystemSettingsService(session_factory), password=None)


def test_resolve_database_config_uses_saved_password_for_test(session_factory: DatabaseSessionFactory) -> None:
    """O teste de conexão com a senha em branco usa a senha já salva."""
    service = SystemSettingsService(session_factory)
    _save_database(service)

    config = service.resolve_database_config(host="outro", port=1433, database="dw", username="carga", password="")

    assert config.host == "outro"
    assert config.password == "S3nh@/forte:%"


def test_clear_minio_config_keeps_database_config(session_factory: DatabaseSessionFactory) -> None:
    """Voltar o MinIO para o .env não pode apagar a conexão do banco (mesma linha singleton)."""
    service = SystemSettingsService(session_factory)
    service.update_minio_config(endpoint="minio:9000", access_key="a", secret_key="s", secure=False)
    _save_database(service)

    service.clear_minio_config()

    assert service.get_minio_config().source == "env"
    assert service.get_database_config() is not None


def test_clear_database_config_removes_connection(session_factory: DatabaseSessionFactory) -> None:
    """Remover a conexão deixa o loader sem URL (cargas passam a registrar erro)."""
    service = SystemSettingsService(session_factory)
    _save_database(service)

    service.clear_database_config()

    assert service.get_database_url() is None
    assert service.get_database_config_for_display()["configured"] is False
