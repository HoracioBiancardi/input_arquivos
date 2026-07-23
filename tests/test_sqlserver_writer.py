"""Testes do SqlServerWriter: lógica de append/create testada contra SQLite local.

SQLite é usado aqui apenas como um banco relacional genérico para validar a
lógica de branching do writer (has_table, append vs. criação versionada), que
é código SQLAlchemy agnóstico de dialeto. Isto NÃO cobre particularidades
específicas do SQL Server real (formato da connection string `pyodbc`,
mapeamento de tipos T-SQL) — essas exigem um SQL Server de verdade, conforme
o plano de verificação manual.
"""

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect

from app.destinations.sqlserver_writer import SchemaMismatchError, SqlServerWriter
from app.ingestion.pipeline import IngestResult
from app.models.context import Context, DestinationType, PdfMode, WriteMode


def _make_context(connection_string: str, table: str = "pedidos") -> Context:
    """Cria um `Context` em memória apontando para o banco de destino de teste."""
    return Context(
        id=1,
        name="vendas",
        destination_type=DestinationType.SQLSERVER,
        db_connection_string=connection_string,
        db_schema_name="main",
        db_table=table,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        active=True,
    )


def _make_artifact(dataframe: pd.DataFrame) -> IngestResult:
    """Cria um `IngestResult` de teste a partir de um DataFrame."""
    return IngestResult(
        artifact_bytes=b"",
        artifact_kind="parquet",
        dataframe=dataframe,
        row_count=len(dataframe),
        page_count=None,
        suggested_filename="pedidos.parquet",
    )


@pytest.fixture
def connection_string(tmp_path: Path) -> str:
    """URL SQLite temporária usada como destino de teste do SqlServerWriter."""
    return f"sqlite:///{tmp_path / 'destino.db'}"


def test_create_new_creates_table_when_absent(connection_string: str) -> None:
    """Em create_new, se a tabela não existir, ela deve ser criada com o nome original."""
    context = _make_context(connection_string)
    artifact = _make_artifact(pd.DataFrame({"contexto": ["vendas"], "valor": [10]}))

    result = SqlServerWriter().write(artifact, context, WriteMode.CREATE_NEW)

    assert result.destination_detail == "main.pedidos"
    engine = create_engine(connection_string)
    assert inspect(engine).has_table("pedidos", schema="main")


def test_create_new_versions_table_when_already_exists(connection_string: str) -> None:
    """Em create_new, se a tabela já existir, uma nova versão com sufixo de timestamp deve ser criada."""
    context = _make_context(connection_string)
    artifact = _make_artifact(pd.DataFrame({"contexto": ["vendas"], "valor": [10]}))
    SqlServerWriter().write(artifact, context, WriteMode.CREATE_NEW)

    result = SqlServerWriter().write(artifact, context, WriteMode.CREATE_NEW)

    assert result.destination_detail != "main.pedidos"
    assert result.destination_detail.startswith("main.pedidos_")


def test_append_falls_back_to_create_when_table_absent(connection_string: str) -> None:
    """Em append, se a tabela não existir, ela deve ser criada (comportamento de fallback)."""
    context = _make_context(connection_string)
    artifact = _make_artifact(pd.DataFrame({"contexto": ["vendas"], "valor": [10]}))

    result = SqlServerWriter().write(artifact, context, WriteMode.APPEND)

    assert result.destination_detail == "main.pedidos"
    assert result.row_count == 1


def test_append_adds_rows_to_existing_table(connection_string: str) -> None:
    """Em append, se a tabela já existir com colunas compatíveis, as linhas devem ser adicionadas."""
    context = _make_context(connection_string)
    first_artifact = _make_artifact(pd.DataFrame({"contexto": ["vendas"], "valor": [10]}))
    SqlServerWriter().write(first_artifact, context, WriteMode.CREATE_NEW)

    second_artifact = _make_artifact(pd.DataFrame({"contexto": ["vendas"], "valor": [20]}))
    SqlServerWriter().write(second_artifact, context, WriteMode.APPEND)

    engine = create_engine(connection_string)
    with engine.connect() as connection:
        total_rows = connection.exec_driver_sql("SELECT COUNT(*) FROM pedidos").scalar()
    assert total_rows == 2


def test_append_raises_on_schema_mismatch(connection_string: str) -> None:
    """Em append, colunas ausentes na tabela existente devem levantar SchemaMismatchError."""
    context = _make_context(connection_string)
    first_artifact = _make_artifact(pd.DataFrame({"contexto": ["vendas"], "valor": [10]}))
    SqlServerWriter().write(first_artifact, context, WriteMode.CREATE_NEW)

    incompatible_artifact = _make_artifact(pd.DataFrame({"coluna_nova": ["x"]}))

    with pytest.raises(SchemaMismatchError):
        SqlServerWriter().write(incompatible_artifact, context, WriteMode.APPEND)
