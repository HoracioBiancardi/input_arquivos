"""Rotas da API REST para consulta e criação de contexts."""

from fastapi import APIRouter

from app.schemas.context import ContextCreateRequest, ContextResponse
from app.services.container import get_container

router = APIRouter(prefix="/api/contexts", tags=["contexts"])


@router.get("", response_model=list[ContextResponse])
def list_contexts(active_only: bool = False) -> list[ContextResponse]:
    """Lista os contexts cadastrados.

    Args:
        active_only: Se `True`, retorna apenas os contexts ativos.

    Returns:
        Lista de contexts convertida para `ContextResponse`.
    """
    context_service = get_container().context_service
    contexts = context_service.list_active() if active_only else context_service.list_all()
    return [ContextResponse.model_validate(context) for context in contexts]


@router.post("", response_model=ContextResponse)
def create_context(payload: ContextCreateRequest) -> ContextResponse:
    """Cria um novo context.

    Args:
        payload: Dados do context a ser criado.

    Returns:
        O context recém-criado, convertido para `ContextResponse`.
    """
    context_service = get_container().context_service
    context = context_service.create(
        name=payload.name,
        destination_type=payload.destination_type,
        default_write_mode=payload.default_write_mode,
        pdf_mode=payload.pdf_mode,
        minio_bucket=payload.minio_bucket,
        db_connection_string=payload.db_connection_string,
        db_schema_name=payload.db_schema_name,
        db_table=payload.db_table,
        local_path=payload.local_path,
        allowed_file_types=payload.allowed_file_types,
    )
    return ContextResponse.model_validate(context)
