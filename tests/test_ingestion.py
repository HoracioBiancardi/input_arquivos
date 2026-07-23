"""Testes do pipeline de ingestão: leitura de Excel/CSV e injeção das colunas de rastreabilidade.

Não há testes de PDF neste arquivo: gerar um PDF de teste exigiria uma
biblioteca de escrita de PDF (ex. reportlab), que não é uma dependência do
projeto. A lógica de leitura de PDF (`PdfTableReader`/`PdfMetadataReader`)
deve ser validada manualmente com um PDF real, conforme o plano de verificação.
"""

import io

import pandas as pd
import pytest

from app.ingestion.pipeline import FileTypeNotAllowedError, IngestionPipeline, UnsupportedFileTypeError
from app.models.context import Context, DestinationType, PdfMode, WriteMode


def _make_context(name: str = "vendas", allowed_file_types: str | None = None) -> Context:
    """Cria um `Context` em memória (sem persistir no banco) para uso nos testes."""
    return Context(
        id=1,
        name=name,
        destination_type=DestinationType.MINIO,
        minio_bucket="vendas",
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        allowed_file_types=allowed_file_types,
        active=True,
    )


def test_process_injects_tracking_columns_for_csv() -> None:
    """As colunas data_envio, contexto e enviado_por devem ser as três primeiras do resultado."""
    csv_bytes = pd.DataFrame({"produto": ["A", "B"], "valor": [1, 2]}).to_csv(index=False).encode("utf-8")

    result = IngestionPipeline().process(csv_bytes, "vendas.csv", _make_context(), uploaded_by="maria")

    assert result.artifact_kind == "parquet"
    assert list(result.dataframe.columns[:3]) == ["data_envio", "contexto", "enviado_por"]
    assert (result.dataframe["contexto"] == "vendas").all()
    assert (result.dataframe["enviado_por"] == "maria").all()
    assert result.row_count == 2


def test_process_strips_utf8_bom_from_csv_columns() -> None:
    """Um CSV com BOM não deve fazer a primeira coluna virar "\\ufeffid" em vez de "id".

    Isso é importante para a checagem de divergência de colunas: sem o tratamento
    do BOM, um arquivo idêntico salvo com/sem BOM pareceria ter colunas diferentes.
    """
    csv_bytes = b"\xef\xbb\xbf" + b"id,valor\n1,10\n2,20\n"

    result = IngestionPipeline().process(csv_bytes, "vendas.csv", _make_context(), uploaded_by="maria")

    assert "id" in result.dataframe.columns
    assert not any(column.startswith("﻿") for column in result.dataframe.columns)


def test_process_reads_excel_file() -> None:
    """Um arquivo Excel deve ser lido e convertido corretamente."""
    buffer = io.BytesIO()
    pd.DataFrame({"produto": ["A", "B"], "valor": [1, 2]}).to_excel(buffer, index=False, engine="openpyxl")

    result = IngestionPipeline().process(buffer.getvalue(), "vendas.xlsx", _make_context(), uploaded_by="joao")

    assert result.row_count == 2
    assert "produto" in result.dataframe.columns


def test_process_raises_for_unsupported_extension() -> None:
    """Extensões não suportadas devem levantar `UnsupportedFileTypeError`."""
    with pytest.raises(UnsupportedFileTypeError):
        IngestionPipeline().process(b"conteudo", "arquivo.txt", _make_context(), uploaded_by="joao")


def test_process_raises_when_file_type_not_allowed_for_context() -> None:
    """Um Excel enviado para um contexto que só aceita CSV deve levantar `FileTypeNotAllowedError`."""
    csv_only_context = _make_context(allowed_file_types="csv")
    buffer = io.BytesIO()
    pd.DataFrame({"produto": ["A"]}).to_excel(buffer, index=False, engine="openpyxl")

    with pytest.raises(FileTypeNotAllowedError):
        IngestionPipeline().process(buffer.getvalue(), "vendas.xlsx", csv_only_context, uploaded_by="joao")


def test_process_allows_file_type_when_context_has_no_restriction() -> None:
    """Sem `allowed_file_types` configurado, o contexto aceita qualquer tipo suportado."""
    unrestricted_context = _make_context(allowed_file_types=None)
    csv_bytes = pd.DataFrame({"produto": ["A"]}).to_csv(index=False).encode("utf-8")

    result = IngestionPipeline().process(csv_bytes, "vendas.csv", unrestricted_context, uploaded_by="joao")

    assert result.row_count == 1
