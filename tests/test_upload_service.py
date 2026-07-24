"""Testes do UploadService: fluxo completo de upload até o registro de auditoria.

Usa a fixture `session_factory` de `tests/conftest.py` (SQLite temporário) e um
context com destino LOCAL (pasta temporária), para exercitar o serviço de
ponta a ponta sem depender de MinIO/SQL Server reais.
"""

from pathlib import Path

import pandas as pd
import pytest

from app.db.session import DatabaseSessionFactory
from app.destinations.registry import DestinationWriterRegistry
from app.ingestion.pipeline import IngestionPipeline
from app.models.context import DestinationType, ImageMode, PdfMode, WriteMode
from app.services.context_service import ContextService
from app.services.upload_service import UploadService


@pytest.fixture
def upload_service(session_factory: DatabaseSessionFactory, tmp_path: Path) -> UploadService:
    """Cria um `UploadService` real, com um context LOCAL já cadastrado."""
    context_service = ContextService(session_factory)
    context_service.create(
        name="vendas",
        destination_type=DestinationType.LOCAL,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.RAW_ARCHIVE,
        image_mode=ImageMode.RAW_ARCHIVE,
        local_path=str(tmp_path),
    )
    return UploadService(
        session_factory=session_factory,
        context_service=context_service,
        pipeline=IngestionPipeline(),
        writer_registry=DestinationWriterRegistry(),
    )


def test_finalize_records_artifact_kind_parquet_for_csv(upload_service: UploadService) -> None:
    """Um CSV normal deve gerar `artifact_kind="parquet"` no audit log."""
    context = upload_service.resolve_context("vendas")
    csv_bytes = pd.DataFrame({"produto": ["A"], "valor": [1]}).to_csv(index=False).encode("utf-8")
    artifact = upload_service.build_artifact(csv_bytes, "vendas.csv", context, uploaded_by="maria")

    history = upload_service.finalize(artifact, context, write_mode=None, filename="vendas.csv", uploaded_by="maria")

    assert history.status.value == "success"
    assert history.artifact_kind == "parquet"
    assert history.row_count == 1


def test_finalize_records_artifact_kind_raw_pdf_for_archive_mode(upload_service: UploadService) -> None:
    """Um PDF em modo raw_archive deve gerar `artifact_kind="raw_pdf"`, sem DataFrame."""
    context = upload_service.resolve_context("vendas")
    artifact = upload_service.build_artifact(b"conteudo-pdf-fake", "arquivo.pdf", context, uploaded_by="joao")

    history = upload_service.finalize(artifact, context, write_mode=None, filename="arquivo.pdf", uploaded_by="joao")

    assert history.status.value == "success"
    assert history.artifact_kind == "raw_pdf"


def test_record_error_leaves_artifact_kind_none(upload_service: UploadService) -> None:
    """Um erro registrado antes de gerar artefato não deve ter `artifact_kind`."""
    context = upload_service.resolve_context("vendas")

    history = upload_service.record_error(context, "arquivo.csv", None, "joao", "falha de leitura")

    assert history.status.value == "error"
    assert history.artifact_kind is None
