"""Testes do PreviewService: reconstrução da tabela gerada por um upload, por tipo de destino.

MinIO não é testado aqui (não há um `test_minio_writer.py` no projeto pelo
mesmo motivo — precisa de um servidor MinIO real; ver plano de verificação
manual).
"""

from pathlib import Path

import pandas as pd
import pytest

from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.destinations.local_writer import LocalFileWriter
from input_arquivos.backend.ingestion.parquet import ParquetConverter
from input_arquivos.backend.ingestion.pipeline import IngestResult
from input_arquivos.backend.models.context import Context, DestinationType, ImageMode, PdfMode
from input_arquivos.backend.models.upload_history import UploadHistory, UploadStatus
from input_arquivos.backend.services.preview_service import (
    PreviewNotAvailableError,
    PreviewService,
    UploadAccessDeniedError,
    UploadNotFoundError,
)


def _make_artifact(dataframe: pd.DataFrame) -> IngestResult:
    """Cria um `IngestResult` de teste com bytes Parquet reais a partir de um DataFrame."""
    return IngestResult(
        artifact_bytes=ParquetConverter().to_bytes(dataframe),
        artifact_kind="parquet",
        dataframe=dataframe,
        row_count=len(dataframe),
        page_count=None,
        suggested_filename="vendas.parquet",
    )


def _add_history(session_factory: DatabaseSessionFactory, **fields: object) -> UploadHistory:
    """Persiste um `UploadHistory` de teste e retorna o registro já com id."""
    defaults = {
        "filename": "vendas.csv",
        "context_name": "vendas",
        "status": UploadStatus.SUCCESS,
        "artifact_kind": "parquet",
        "row_count": None,
        "error_message": None,
        "uploaded_by": "maria",
    }
    history = UploadHistory(**{**defaults, **fields})
    with session_factory.session() as db_session:
        db_session.add(history)
        db_session.flush()
        db_session.refresh(history)
        db_session.expunge(history)
    return history


def test_get_preview_reads_local_parquet(session_factory: DatabaseSessionFactory, tmp_path: Path) -> None:
    """Um upload LOCAL deve ser lido de volta direto do caminho salvo em `destination_detail`."""
    dataframe = pd.DataFrame({"produto": ["A", "B"], "valor": [1, 2]})
    context = Context(
        id=1, name="vendas", destination_type=DestinationType.LOCAL, local_path=str(tmp_path),
        pdf_mode=PdfMode.METADATA_ONLY, image_mode=ImageMode.RAW_ARCHIVE,
        active=True,
    )
    write_result = LocalFileWriter().write(_make_artifact(dataframe), context)
    history = _add_history(
        session_factory, destination_type=DestinationType.LOCAL,
        destination_detail=write_result.destination_detail, row_count=2,
    )

    preview = PreviewService(session_factory).get_preview(history.id)

    assert preview.filename == "vendas.csv"
    assert preview.columns == ["produto", "valor"]
    assert preview.rows == [["A", 1], ["B", 2]]
    assert preview.total_row_count == 2
    assert preview.truncated is False


def test_get_preview_raises_when_not_available(session_factory: DatabaseSessionFactory) -> None:
    """Um upload arquivado sem processar (raw_pdf) não tem tabela para visualizar."""
    history = _add_history(
        session_factory, destination_type=DestinationType.LOCAL, destination_detail="/tmp/arquivo.pdf",
        artifact_kind="raw_pdf",
    )

    with pytest.raises(PreviewNotAvailableError):
        PreviewService(session_factory).get_preview(history.id)


def test_get_preview_raises_for_failed_upload(session_factory: DatabaseSessionFactory) -> None:
    """Um upload com status de erro não tem tabela para visualizar."""
    history = _add_history(
        session_factory, destination_type=DestinationType.LOCAL, destination_detail="",
        status=UploadStatus.ERROR, artifact_kind=None, error_message="falhou",
    )

    with pytest.raises(PreviewNotAvailableError):
        PreviewService(session_factory).get_preview(history.id)


def test_get_preview_raises_when_upload_not_found(session_factory: DatabaseSessionFactory) -> None:
    """Um id inexistente deve levantar `UploadNotFoundError`."""
    with pytest.raises(UploadNotFoundError):
        PreviewService(session_factory).get_preview(999)


def test_get_preview_denies_access_to_context_outside_allowed_set(
    session_factory: DatabaseSessionFactory, tmp_path: Path
) -> None:
    """Um usuário sem acesso ao context do upload não deve conseguir ver o preview (IDOR).

    Antes da correção, `get_preview` não recebia nenhuma informação sobre
    quem estava pedindo o preview — qualquer usuário autenticado conseguia
    ler dados de qualquer context só iterando `upload_id`.
    """
    dataframe = pd.DataFrame({"produto": ["A"], "valor": [1]})
    context = Context(
        id=1, name="vendas", destination_type=DestinationType.LOCAL, local_path=str(tmp_path),
        pdf_mode=PdfMode.METADATA_ONLY, image_mode=ImageMode.RAW_ARCHIVE,
        active=True,
    )
    write_result = LocalFileWriter().write(_make_artifact(dataframe), context)
    history = _add_history(
        session_factory, destination_type=DestinationType.LOCAL,
        destination_detail=write_result.destination_detail, row_count=1,
    )

    service = PreviewService(session_factory)

    with pytest.raises(UploadAccessDeniedError):
        service.get_preview(history.id, allowed_context_names={"outro-contexto"})

    # Com o context correto no conjunto permitido, o preview funciona normalmente.
    preview = service.get_preview(history.id, allowed_context_names={"vendas"})
    assert preview.columns == ["produto", "valor"]
