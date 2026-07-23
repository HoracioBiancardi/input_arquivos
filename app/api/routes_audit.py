"""Rota da API REST para consulta do audit log de uploads."""

from datetime import date

from fastapi import APIRouter, Depends

from app.auth.dependencies import require_admin
from app.models.upload_history import UploadStatus
from app.schemas.upload import UploadHistoryResponse
from app.services.container import get_container

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
