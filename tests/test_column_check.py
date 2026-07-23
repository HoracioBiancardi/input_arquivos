"""Testes do ColumnMismatchChecker: detecção de divergência de colunas entre uploads."""

import pandas as pd

from app.models.context import Context, DestinationType, PdfMode, WriteMode
from app.services.column_check import ColumnMismatchChecker


def _make_context(expected_columns: str | None) -> Context:
    """Cria um `Context` em memória com um valor de `expected_columns` para os testes."""
    return Context(
        id=1,
        name="vendas",
        destination_type=DestinationType.LOCAL,
        local_path=None,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        expected_columns=expected_columns,
        active=True,
    )


def _tracked_dataframe(columns: list[str]) -> pd.DataFrame:
    """Simula o DataFrame já com as colunas de rastreabilidade injetadas pelo pipeline."""
    data = {"data_envio": ["x"], "contexto": ["vendas"], "enviado_por": ["maria"]}
    for column in columns:
        data[column] = ["valor"]
    return pd.DataFrame(data)


def test_check_returns_none_on_first_upload() -> None:
    """Sem `expected_columns` registrado ainda, não há divergência a reportar."""
    context = _make_context(expected_columns=None)
    dataframe = _tracked_dataframe(["produto", "valor"])

    assert ColumnMismatchChecker().check(context, dataframe) is None


def test_check_returns_none_when_columns_match() -> None:
    """Colunas idênticas às anteriores não geram divergência."""
    context = _make_context(expected_columns="produto,valor")
    dataframe = _tracked_dataframe(["produto", "valor"])

    assert ColumnMismatchChecker().check(context, dataframe) is None


def test_check_detects_missing_and_extra_columns() -> None:
    """Colunas removidas e adicionadas devem ser reportadas corretamente."""
    context = _make_context(expected_columns="produto,valor")
    dataframe = _tracked_dataframe(["produto", "quantidade"])

    mismatch = ColumnMismatchChecker().check(context, dataframe)

    assert mismatch is not None
    assert mismatch.missing_columns == ["valor"]
    assert mismatch.extra_columns == ["quantidade"]


def test_serialize_excludes_tracking_columns() -> None:
    """A serialização usada para salvar `expected_columns` não deve incluir as colunas injetadas."""
    dataframe = _tracked_dataframe(["produto", "valor"])

    serialized = ColumnMismatchChecker().serialize(dataframe)

    assert serialized == "produto,valor"
