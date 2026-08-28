"""Fixtures compartilhadas pelos testes automatizados."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from input_arquivos.backend.config import get_settings
from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.models.base import Base
from input_arquivos.backend.models.context import Context  # noqa: F401 - garante o registro do modelo no metadata
from input_arquivos.backend.models.system_settings import SystemSettings  # noqa: F401 - garante o registro do modelo no metadata
from input_arquivos.backend.models.upload_history import UploadHistory  # noqa: F401 - garante o registro do modelo no metadata
from input_arquivos.backend.models.user import User  # noqa: F401 - garante o registro do modelo no metadata
from input_arquivos.backend.models.user_context_access import user_context_access  # noqa: F401 - garante o registro no metadata
from input_arquivos.backend.security import secret_box


@pytest.fixture
def session_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[DatabaseSessionFactory]:
    """Cria uma `DatabaseSessionFactory` isolada, apoiada em um SQLite temporário por teste.

    Também isola `APP_CONFIG_DB_PATH` (e limpa os caches de `get_settings`
    e `secret_box`) para este `tmp_path`: sem isso, `EncryptedString`
    resolveria a chave de cifragem via `get_settings().app_config_db_path`
    "de verdade" (aponta pro `data/` real do projeto sempre que nenhum
    teste tiver feito override antes), criando um `.config_encryption_key`
    real como efeito colateral de rodar a suíte — qualquer teste que toque
    `SystemSettings.minio_access_key`/`minio_secret_key` (cifrados) dispara
    essa resolução.

    Args:
        tmp_path: Diretório temporário único fornecido pelo pytest para este teste.
        monkeypatch: Fixture do pytest para setar variáveis de ambiente.

    Yields:
        Fábrica de sessões com as tabelas da aplicação já criadas.
    """
    monkeypatch.setenv("APP_CONFIG_DB_PATH", str(tmp_path / "test_app_config.db"))
    get_settings.cache_clear()
    secret_box.reset_for_testing()

    database_url = f"sqlite:///{tmp_path / 'test_app_config.db'}"
    factory = DatabaseSessionFactory(database_url=database_url)
    Base.metadata.create_all(factory.engine)
    yield factory

    get_settings.cache_clear()
    secret_box.reset_for_testing()
