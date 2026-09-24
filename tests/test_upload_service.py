"""Testes do UploadService: fluxo completo de upload até o registro de auditoria.

Usa a fixture `session_factory` de `tests/conftest.py` (SQLite temporário) e um
context com destino LOCAL (pasta temporária), para exercitar o serviço de
ponta a ponta sem depender de um MinIO real.
"""

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine

from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.destinations.registry import DestinationWriterRegistry
from input_arquivos.backend.ingestion.pipeline import IngestionPipeline
from input_arquivos.backend.loaders.database_loader import DatabaseLoader
from input_arquivos.backend.models.context import DestinationType, ImageMode, PdfMode
from input_arquivos.backend.services.context_service import ContextService
from input_arquivos.backend.models.upload_history import LoadStatus, UploadStatus
from input_arquivos.backend.services.upload_service import LoadNotApplicableError, UploadNotFoundError, UploadService


@pytest.fixture
def upload_service(session_factory: DatabaseSessionFactory, tmp_path: Path) -> UploadService:
    """Cria um `UploadService` real, com um context LOCAL já cadastrado."""
    context_service = ContextService(session_factory)
    context_service.create(
        name="vendas",
        destination_type=DestinationType.LOCAL,
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

    history = upload_service.finalize(artifact, context, filename="vendas.csv", uploaded_by="maria")

    assert history.status.value == "success"
    assert history.artifact_kind == "parquet"
    assert history.row_count == 1


def test_finalize_records_artifact_kind_raw_pdf_for_archive_mode(upload_service: UploadService) -> None:
    """Um PDF em modo raw_archive deve gerar `artifact_kind="raw_pdf"`, sem DataFrame."""
    context = upload_service.resolve_context("vendas")
    artifact = upload_service.build_artifact(b"conteudo-pdf-fake", "arquivo.pdf", context, uploaded_by="joao")

    history = upload_service.finalize(artifact, context, filename="arquivo.pdf", uploaded_by="joao")

    assert history.status.value == "success"
    assert history.artifact_kind == "raw_pdf"


def test_record_error_leaves_artifact_kind_none(upload_service: UploadService) -> None:
    """Um erro registrado antes de gerar artefato não deve ter `artifact_kind`."""
    context = upload_service.resolve_context("vendas")

    history = upload_service.record_error(context, "arquivo.csv", "joao", "falha de leitura")

    assert history.status.value == "error"
    assert history.artifact_kind is None


@pytest.fixture
def loading_upload_service(session_factory: DatabaseSessionFactory, tmp_path: Path) -> tuple[UploadService, dict]:
    """`UploadService` com um context LOCAL que carrega no banco; o banco de destino é um SQLite temporário.

    Returns:
        O serviço e um dict mutável `{"url": ...}` — trocar a URL simula o
        banco fora do ar/não configurado sem recriar o serviço.
    """
    context_service = ContextService(session_factory)
    context_service.create(
        name="vendas",
        destination_type=DestinationType.LOCAL,
        pdf_mode=PdfMode.RAW_ARCHIVE,
        local_path=str(tmp_path / "arquivos"),
        load_to_database=True,
    )
    target = {"url": f"sqlite:///{tmp_path / 'destino.db'}"}
    service = UploadService(
        session_factory=session_factory,
        context_service=context_service,
        pipeline=IngestionPipeline(),
        writer_registry=DestinationWriterRegistry(),
        database_loader=DatabaseLoader(lambda: target["url"]),
    )
    return service, target


def _csv(produtos: list[str]) -> bytes:
    """CSV mínimo com uma coluna de produto."""
    return pd.DataFrame({"produto": produtos}).to_csv(index=False).encode("utf-8")


def test_process_upload_loads_parquet_into_context_table(loading_upload_service: tuple[UploadService, dict]) -> None:
    """Via API, o upload grava o Parquet e já carrega as linhas na tabela do context."""
    service, target = loading_upload_service

    history = service.process_upload(_csv(["A", "B"]), "vendas.csv", "vendas", uploaded_by="maria")

    assert history.status == UploadStatus.SUCCESS
    assert history.load_status == LoadStatus.SUCCESS
    assert history.load_detail == "vendas"
    assert history.loaded_at is not None
    engine = create_engine(target["url"])
    table = pd.read_sql_table("vendas", engine)
    engine.dispose()
    assert table["id_envio"].tolist() == [history.id, history.id]


def test_finalize_marks_load_pending_only_for_parquet(loading_upload_service: tuple[UploadService, dict]) -> None:
    """`finalize` deixa a carga pendente para Parquet e não se aplica a PDF arquivado."""
    service, _ = loading_upload_service
    context = service.resolve_context("vendas")

    csv_artifact = service.build_artifact(_csv(["A"]), "vendas.csv", context, uploaded_by="maria")
    pdf_artifact = service.build_artifact(b"pdf-fake", "nota.pdf", context, uploaded_by="maria")

    assert service.finalize(csv_artifact, context, "vendas.csv", "maria").load_status == LoadStatus.PENDING
    assert service.finalize(pdf_artifact, context, "nota.pdf", "maria").load_status is None


def test_load_failure_keeps_upload_and_reload_reads_from_destination(
    loading_upload_service: tuple[UploadService, dict], tmp_path: Path
) -> None:
    """Banco fora do ar não desfaz o upload; recarregar depois lê o Parquet da pasta/MinIO e carrega."""
    service, target = loading_upload_service
    working_url = target["url"]
    target["url"] = None

    history = service.process_upload(_csv(["A"]), "vendas.csv", "vendas", uploaded_by="maria")

    assert history.status == UploadStatus.SUCCESS
    assert history.load_status == LoadStatus.ERROR
    assert "não configurado" in history.load_error

    target["url"] = working_url
    reloaded = service.run_database_load(history.id)

    assert reloaded.load_status == LoadStatus.SUCCESS
    assert reloaded.load_error is None


def test_run_database_load_rejects_context_with_load_disabled(
    loading_upload_service: tuple[UploadService, dict],
) -> None:
    """Recarregar um envio de um context com a carga desligada é recusado sem mexer no histórico."""
    service, _ = loading_upload_service
    history = service.process_upload(_csv(["A"]), "vendas.csv", "vendas", uploaded_by="maria")
    context = service.resolve_context("vendas")
    service._context_service.update(context.id, load_to_database=False)

    with pytest.raises(LoadNotApplicableError, match="desligada"):
        service.run_database_load(history.id)


def test_run_database_load_rejects_unknown_upload(loading_upload_service: tuple[UploadService, dict]) -> None:
    """Um id inexistente levanta `UploadNotFoundError`."""
    service, _ = loading_upload_service
    with pytest.raises(UploadNotFoundError):
        service.run_database_load(9999)
