"""Testes do SystemSettingsService: configuração global do MinIO (admin, com fallback pro .env)."""

import pytest

from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.services.system_settings_service import (
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
