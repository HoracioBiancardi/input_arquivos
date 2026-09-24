"""Rota da API REST para consulta do audit log de uploads."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException

from input_arquivos.backend.auth.dependencies import require_admin
from input_arquivos.backend.models.upload_history import UploadStatus
from input_arquivos.backend.schemas.upload import UploadHistoryResponse
from input_arquivos.backend.services.container import get_container
from input_arquivos.backend.services.upload_service import LoadNotApplicableError, UploadNotFoundError

router = APIRouter(prefix="/api/audit", tags=["audit"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UploadHistoryResponse])
def list_audit_log(
    context_name: str | None = None,
    status: UploadStatus | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 200,
) -> list[UploadHistoryResponse]:
    """Lista o audit log de uploads, com filtros opcionais.

    Args:
        context_name: Filtra por nome de contexto.
        status: Filtra por status (sucesso/erro).
        start_date: Data inicial (inclusive) do período.
        end_date: Data final (inclusive) do período.
        limit: Quantidade máxima de registros a retornar.

    Returns:
        Lista de registros de audit log convertidos para `UploadHistoryResponse`.
    """
    upload_service = get_container().upload_service
    history = upload_service.list_filtered(
        context_name=context_name, status=status, start_date=start_date, end_date=end_date, limit=limit
    )
    return [UploadHistoryResponse.model_validate(item) for item in history]


@router.post("/{upload_id}/load", response_model=UploadHistoryResponse)
def reload_to_database(upload_id: int) -> UploadHistoryResponse:
    """Carrega de novo um upload na tabela do seu context, lendo o Parquet do MinIO/pasta local.

    Usado para refazer uma carga que falhou (banco fora do ar, tabela sem uma
    coluna nova) ou que ficou pendente (servidor reiniciado no meio). No modo
    append, as linhas anteriores deste upload são substituídas — nunca duplicadas.

    Args:
        upload_id: Identificador do upload.

    Returns:
        O registro de audit log com a nova situação da carga.

    Raises:
        HTTPException: 404 se o upload não existir; 409 se ele não puder ser
            carregado (não gerou tabela, ou o context está com a carga desligada).
    """
    try:
        history = get_container().upload_service.run_database_load(upload_id)
    except UploadNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except LoadNotApplicableError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return UploadHistoryResponse.model_validate(history)
