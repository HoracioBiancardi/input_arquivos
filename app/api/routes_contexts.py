"""Rotas da API REST para consulta, criação, edição e teste de conectividade de contexts."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import require_admin, require_login
from app.auth.session import SessionUser
from app.ingestion.file_types import FileTypeRegistry
from app.models.context import Context, DestinationType
from app.schemas.context import (
    AccessibleContextResponse,
    AccessibleContextsResponse,
    ConnectionTestResponse,
    ContextCreateRequest,
    ContextResponse,
    ContextUpdateRequest,
    DbConnectionTestRequest,
    LocalConnectionTestRequest,
    MinioConnectionTestRequest,
)
from app.services.container import get_container
from app.services.context_service import DuplicateNameError

router = APIRouter(prefix="/api/contexts", tags=["contexts"])


def _describe_destination(context: Context) -> str:
    """Monta uma descrição curta do destino de um context, para exibição na UI.

    Args:
        context: Context a descrever.

    Returns:
        Texto descrevendo o destino ("MinIO → bucket", "SQL Server →
        schema.tabela" ou "Local → pasta").
    """
    if context.destination_type == DestinationType.MINIO:
        return f"MinIO → {context.minio_bucket}"
    if context.destination_type == DestinationType.LOCAL:
        return f"Local → {context.local_path}"
    return f"SQL Server → {context.db_schema_name}.{context.db_table}"


def _to_response(context: Context) -> ContextResponse:
    """Converte um `Context` para `ContextResponse`, incluindo o resumo do destino.

    Args:
        context: Context a converter.

    Returns:
        Representação do context pronta para a API.
    """
    response = ContextResponse.model_validate(context)
    response.destination_summary = _describe_destination(context)
    return response


@router.get("", response_model=list[ContextResponse], dependencies=[Depends(require_login)])
def list_contexts(active_only: bool = False) -> list[ContextResponse]:
    """Lista os contexts cadastrados.

    Args:
        active_only: Se `True`, retorna apenas os contexts ativos.

    Returns:
        Lista de contexts convertida para `ContextResponse`.
    """
    context_service = get_container().context_service
    contexts = context_service.list_active() if active_only else context_service.list_all()
    return [_to_response(context) for context in contexts]


@router.get("/me/accessible", response_model=AccessibleContextsResponse, dependencies=[Depends(require_login)])
def list_accessible_contexts(user: SessionUser = Depends(require_login)) -> AccessibleContextsResponse:
    """Lista os contexts ativos que o usuário atual pode usar na tela de upload.

    Args:
        user: Usuário autenticado na sessão atual.

    Returns:
        Contexts acessíveis ao usuário, mais um indicador de existência de
        contexts ativos no sistema (para diferenciar os dois motivos de a
        lista estar vazia).
    """
    container = get_container()
    current_user = container.user_service.get_by_id(user.user_id)
    if current_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário não encontrado.")

    file_type_registry = FileTypeRegistry()
    has_any_active_context = bool(container.context_service.list_active())
    contexts = container.user_context_service.list_accessible_contexts(current_user)
    accessible_names = {context.name for context in contexts}
    last_context_name = (
        current_user.last_context_name if current_user.last_context_name in accessible_names else None
    )

    return AccessibleContextsResponse(
        has_any_active_context=has_any_active_context,
        last_context_name=last_context_name,
        contexts=[
            AccessibleContextResponse(
                id=context.id,
                name=context.name,
                destination_type=context.destination_type,
                minio_bucket=context.minio_bucket,
                db_schema_name=context.db_schema_name,
                db_table=context.db_table,
                local_path=context.local_path,
                default_write_mode=context.default_write_mode,
                allowed_extensions=file_type_registry.extensions_for_types(
                    file_type_registry.deserialize(context.allowed_file_types)
                ),
            )
            for context in contexts
        ],
    )


@router.get("/{context_id}", response_model=ContextResponse, dependencies=[Depends(require_admin)])
def get_context(context_id: int) -> ContextResponse:
    """Busca um context pelo identificador.

    Args:
        context_id: Identificador do context.

    Returns:
        O context encontrado, convertido para `ContextResponse`.

    Raises:
        HTTPException: 404 se o context não existir.
    """
    context = get_container().context_service.get_by_id(context_id)
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Context não encontrado.")
    return _to_response(context)


@router.post("", response_model=ContextResponse, dependencies=[Depends(require_admin)])
def create_context(payload: ContextCreateRequest) -> ContextResponse:
    """Cria um novo context.

    Args:
        payload: Dados do context a ser criado.

    Returns:
        O context recém-criado, convertido para `ContextResponse`.

    Raises:
        HTTPException: 409 se já existir um context com esse nome.
    """
    context_service = get_container().context_service
    try:
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
            required_columns=payload.required_columns,
        )
    except DuplicateNameError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"field": "name", "message": str(error)}
        ) from error
    return _to_response(context)


@router.put("/{context_id}", response_model=ContextResponse, dependencies=[Depends(require_admin)])
def update_context(context_id: int, payload: ContextUpdateRequest) -> ContextResponse:
    """Atualiza um context existente.

    Args:
        context_id: Identificador do context a atualizar.
        payload: Novos dados do context.

    Returns:
        O context atualizado, convertido para `ContextResponse`.

    Raises:
        HTTPException: 404 se o context não existir, ou 409 se o novo nome já
            pertencer a outro context.
    """
    try:
        context = get_container().context_service.update(
            context_id,
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
            required_columns=payload.required_columns or None,
            active=payload.active,
        )
    except DuplicateNameError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"field": "name", "message": str(error)}
        ) from error
    if context is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Context não encontrado.")
    return _to_response(context)


@router.post("/test-minio", response_model=ConnectionTestResponse, dependencies=[Depends(require_admin)])
def test_minio_connection(payload: MinioConnectionTestRequest) -> ConnectionTestResponse:
    """Testa a conectividade com um bucket MinIO.

    Args:
        payload: Bucket a testar.

    Returns:
        Resultado do teste de conectividade.
    """
    result = get_container().context_service.test_minio_connection(payload.bucket)
    return ConnectionTestResponse(success=result.success, message=result.message)


@router.post("/test-db", response_model=ConnectionTestResponse, dependencies=[Depends(require_admin)])
def test_db_connection(payload: DbConnectionTestRequest) -> ConnectionTestResponse:
    """Testa a conectividade com um banco de dados de destino.

    Args:
        payload: Connection string a testar.

    Returns:
        Resultado do teste de conectividade.
    """
    result = get_container().context_service.test_db_connection(payload.connection_string)
    return ConnectionTestResponse(success=result.success, message=result.message)


@router.post("/test-local", response_model=ConnectionTestResponse, dependencies=[Depends(require_admin)])
def test_local_path(payload: LocalConnectionTestRequest) -> ConnectionTestResponse:
    """Testa/cria uma pasta local de destino.

    Args:
        payload: Caminho da pasta a testar.

    Returns:
        Resultado do teste de conectividade.
    """
    result = get_container().context_service.test_local_path(payload.path)
    return ConnectionTestResponse(success=result.success, message=result.message)
