"""Fixtures compartilhadas pelos testes automatizados."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db.session import DatabaseSessionFactory
from app.models.base import Base
from app.models.context import Context  # noqa: F401 - garante o registro do modelo no metadata
from app.models.upload_history import UploadHistory  # noqa: F401 - garante o registro do modelo no metadata
from app.models.user import User  # noqa: F401 - garante o registro do modelo no metadata
from app.models.user_context_access import user_context_access  # noqa: F401 - garante o registro no metadata


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[DatabaseSessionFactory]:
    """Cria uma `DatabaseSessionFactory` isolada, apoiada em um SQLite temporário por teste.

    Args:
        tmp_path: Diretório temporário único fornecido pelo pytest para este teste.

    Yields:
        Fábrica de sessões com as tabelas da aplicação já criadas.
    """
    database_url = f"sqlite:///{tmp_path / 'test_app_config.db'}"
    factory = DatabaseSessionFactory(database_url=database_url)
    Base.metadata.create_all(factory.engine)
    yield factory
