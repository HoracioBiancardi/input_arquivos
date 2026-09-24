"""Testes do DatabaseLoader: carga do Parquet de um upload na tabela do context.

O banco de destino dos testes é um SQLite temporário — o loader só fala
SQLAlchemy, então o comportamento de criação/append/replace é o mesmo do
SQL Server (a allowlist de dialetos vale só para a URL salva pelo admin).
"""

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect

from input_arquivos.backend.ingestion.parquet import ParquetConverter
from input_arquivos.backend.loaders.database_loader import (
    DatabaseLoader,
    DatabaseNotConfiguredError,
    TableSchemaMismatchError,
    describe_target_table,
)
from input_arquivos.backend.models.context import Context, DestinationType, LoadMode


def _context(**overrides: object) -> Context:
    """Monta um context em memória com carga no banco ligada."""
    fields = {
        "name": "Relatório Vendas",
        "destination_type": DestinationType.LOCAL,
        "load_to_database": True,
        "db_schema": None,
        "db_table": None,
        "load_mode": LoadMode.APPEND,
    }
    fields.update(overrides)
    return Context(**fields)


def _parquet(produtos: list[str], extra: dict[str, list[object]] | None = None) -> bytes:
    """Gera um Parquet com os tipos que o pipeline produz (tracking + colunas regradas)."""
    size = len(produtos)
    data: dict[str, object] = {
        "data_envio": [datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)] * size,
        "contexto": ["Relatório Vendas"] * size,
        "enviado_por": ["maria"] * size,
        "produto": pd.array(produtos, dtype="string"),
        "quantidade": pd.array(list(range(size)), dtype="Int64"),
        "valor": pd.array([1.5] * size, dtype="Float64"),
        "vencimento": [date(2026, 1, 31)] * size,
        "ativo": pd.array([True] * size, dtype="boolean"),
    }
    data.update(extra or {})
    return ParquetConverter().to_bytes(pd.DataFrame(data))


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    """URL de um SQLite temporário fazendo o papel do banco de destino."""
    return f"sqlite:///{tmp_path / 'destino.db'}"


def _read_table(database_url: str, table: str) -> pd.DataFrame:
    """Lê a tabela inteira do banco de destino, ordenada por `id_envio`."""
    engine = create_engine(database_url)
    try:
        return pd.read_sql_table(table, engine).sort_values(["id_envio", "produto"]).reset_index(drop=True)
    finally:
        engine.dispose()


def test_first_load_creates_table_named_after_context_slug(database_url: str) -> None:
    """Sem tabela informada, a tabela recebe o slug do context e ganha `id_envio`."""
    loader = DatabaseLoader(lambda: database_url)

    result = loader.load(_parquet(["A", "B"]), _context(), upload_id=7)

    assert result.table == "relatorio_vendas"
    assert result.row_count == 2
    table = _read_table(database_url, "relatorio_vendas")
    assert list(table.columns[:4]) == ["id_envio", "data_envio", "contexto", "enviado_por"]
    assert table["id_envio"].tolist() == [7, 7]
    assert table["produto"].tolist() == ["A", "B"]


def test_append_accumulates_uploads_and_reload_does_not_duplicate(database_url: str) -> None:
    """Modo append soma envios diferentes; recarregar o mesmo envio substitui só as linhas dele."""
    loader = DatabaseLoader(lambda: database_url)
    context = _context()

    loader.load(_parquet(["A", "B"]), context, upload_id=1)
    loader.load(_parquet(["C"]), context, upload_id=2)
    loader.load(_parquet(["A", "B"]), context, upload_id=1)

    table = _read_table(database_url, "relatorio_vendas")
    assert table["id_envio"].tolist() == [1, 1, 2]
    assert table["produto"].tolist() == ["A", "B", "C"]


def test_replace_keeps_only_last_upload(database_url: str) -> None:
    """Modo replace apaga o conteúdo anterior da tabela antes de inserir."""
    loader = DatabaseLoader(lambda: database_url)
    context = _context(load_mode=LoadMode.REPLACE, db_table="estoque_atual")

    loader.load(_parquet(["A", "B"]), context, upload_id=1)
    loader.load(_parquet(["C"]), context, upload_id=2)

    table = _read_table(database_url, "estoque_atual")
    assert table["id_envio"].tolist() == [2]
    assert table["produto"].tolist() == ["C"]


def test_new_column_in_file_is_rejected_without_touching_table(database_url: str) -> None:
    """Uma coluna que a tabela não tem gera erro claro e não apaga as linhas existentes."""
    loader = DatabaseLoader(lambda: database_url)
    context = _context()
    loader.load(_parquet(["A"]), context, upload_id=1)

    with pytest.raises(TableSchemaMismatchError, match="desconto"):
        loader.load(_parquet(["B"], extra={"desconto": [0.1]}), context, upload_id=2)

    assert _read_table(database_url, "relatorio_vendas")["produto"].tolist() == ["A"]


def test_existing_table_without_upload_id_column_is_rejected(database_url: str) -> None:
    """Uma tabela criada fora do sistema (sem `id_envio`) nunca recebe carga."""
    engine = create_engine(database_url)
    pd.DataFrame({"produto": ["X"]}).to_sql("relatorio_vendas", engine, index=False)
    engine.dispose()

    with pytest.raises(TableSchemaMismatchError, match="id_envio"):
        DatabaseLoader(lambda: database_url).load(_parquet(["A"]), _context(), upload_id=1)


def test_missing_database_url_raises_not_configured() -> None:
    """Sem conexão configurada, a carga falha com mensagem que aponta para as configurações."""
    with pytest.raises(DatabaseNotConfiguredError, match="Configurações"):
        DatabaseLoader(lambda: None).load(_parquet(["A"]), _context(), upload_id=1)


def test_table_uses_sql_types_for_ruled_columns(database_url: str) -> None:
    """Colunas tipadas no Parquet viram colunas SQL tipadas (não texto) na criação da tabela."""
    DatabaseLoader(lambda: database_url).load(_parquet(["A"]), _context(), upload_id=1)

    engine = create_engine(database_url)
    columns = {column["name"]: str(column["type"]) for column in inspect(engine).get_columns("relatorio_vendas")}
    engine.dispose()
    assert columns["id_envio"] == "BIGINT"
    assert columns["quantidade"] == "BIGINT"
    assert columns["vencimento"] == "DATE"
    assert columns["ativo"] == "BOOLEAN"
    assert columns["data_envio"] == "DATETIME"


def test_describe_target_table_includes_schema_when_set() -> None:
    """Schema informado aparece como prefixo; sem schema, só o nome da tabela."""
    assert describe_target_table(_context(db_schema="staging", db_table="vendas")) == "staging.vendas"
    assert describe_target_table(_context()) == "relatorio_vendas"
