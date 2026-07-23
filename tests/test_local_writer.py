"""Testes do LocalFileWriter: escrita de artefatos em uma pasta local, sem depender de MinIO/SQL Server."""

from pathlib import Path

import pandas as pd
import pytest

from app.destinations.local_writer import LocalFileWriter
from app.ingestion.pipeline import IngestResult
from app.models.context import Context, DestinationType, PdfMode, WriteMode


def _make_context(local_path: str | None) -> Context:
    """Cria um `Context` em memória do tipo LOCAL para uso nos testes."""
    return Context(
        id=1,
        name="vendas",
        destination_type=DestinationType.LOCAL,
        local_path=local_path,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        active=True,
    )


def test_write_saves_parquet_artifact_under_local_path(tmp_path: Path) -> None:
    """Um artefato Parquet deve ser salvo dentro da pasta local do contexto, particionado por data."""
    context = _make_context(str(tmp_path))
    artifact = IngestResult(
        artifact_bytes=b"conteudo-parquet-fake",
        artifact_kind="parquet",
        dataframe=pd.DataFrame({"contexto": ["vendas"]}),
        row_count=1,
        page_count=None,
        suggested_filename="vendas.parquet",
    )

    result = LocalFileWriter().write(artifact, context, write_mode=None)

    written_path = Path(result.destination_detail)
    assert written_path.exists()
    assert written_path.read_bytes() == b"conteudo-parquet-fake"
    assert written_path.is_relative_to(tmp_path)
    assert result.row_count == 1


def test_write_defaults_to_current_directory_when_local_path_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem `local_path` configurado, os arquivos devem ser salvos a partir do diretório de trabalho atual."""
    monkeypatch.chdir(tmp_path)
    context = _make_context(local_path=None)
    artifact = IngestResult(
        artifact_bytes=b"x",
        artifact_kind="parquet",
        dataframe=pd.DataFrame({"a": [1]}),
        row_count=1,
        page_count=None,
        suggested_filename="a.parquet",
    )

    result = LocalFileWriter().write(artifact, context, write_mode=None)

    written_path = Path(result.destination_detail)
    assert written_path.exists()
    assert written_path.is_relative_to(tmp_path)
