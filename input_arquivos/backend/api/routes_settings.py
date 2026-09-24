"""Rotas da API REST para a configuração global do MinIO e do SQL Server de destino (admin-only)."""

from fastapi import APIRouter, Depends, HTTPException, status

from input_arquivos.backend.auth.dependencies import require_admin
from input_arquivos.backend.schemas.context import ConnectionTestResponse
from input_arquivos.backend.loaders.database_loader import check_database_connection
from input_arquivos.backend.schemas.system_settings import (
    DatabaseConfigRequest,
    DatabaseConfigResponse,
    MinioConfigResponse,
    MinioConfigTestRequest,
    MinioConfigUpdateRequest,
)
from input_arquivos.backend.services.container import get_container
from input_arquivos.backend.services.system_settings_service import (
    DatabaseConfigIncompleteError,
    MinioConfigIncompleteError,
)

router = APIRouter(prefix="/api/settings", tags=["settings"], dependencies=[Depends(require_admin)])


@router.get("/minio", response_model=MinioConfigResponse)
def get_minio_config() -> MinioConfigResponse:
    """Retorna a configuração do MinIO atualmente em uso (salva via admin, ou `.env` como fallback).

    Returns:
        Configuração do MinIO, sem expor a chave secreta em texto puro.
    """
    data = get_container().system_settings_service.get_minio_config_for_display()
    return MinioConfigResponse(**data)


@router.put("/minio", response_model=MinioConfigResponse)
def update_minio_config(payload: MinioConfigUpdateRequest) -> MinioConfigResponse:
    """Salva a configuração do MinIO, sobrepondo o `.env` para todos os contexts do tipo MinIO.

    Args:
        payload: Novo endpoint/credenciais/flag de HTTPS.

    Returns:
        Configuração do MinIO já atualizada.

    Raises:
        HTTPException: 422 se não houver chave secreta informada nem uma já
            salva anteriormente.
    """
    container = get_container()
    try:
        container.system_settings_service.update_minio_config(
            endpoint=payload.endpoint,
            access_key=payload.access_key,
            secret_key=payload.secret_key,
            secure=payload.secure,
        )
    except MinioConfigIncompleteError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    data = container.system_settings_service.get_minio_config_for_display()
    return MinioConfigResponse(**data)


@router.delete("/minio", status_code=status.HTTP_204_NO_CONTENT)
def clear_minio_config() -> None:
    """Remove a configuração do MinIO salva via admin, voltando a usar o `.env`."""
    get_container().system_settings_service.clear_minio_config()


@router.post("/minio/test", response_model=ConnectionTestResponse)
def test_minio_config(payload: MinioConfigTestRequest) -> ConnectionTestResponse:
    """Testa conectividade com um endpoint/credenciais de MinIO ainda não salvos.

    Args:
        payload: Endpoint/credenciais a testar.

    Returns:
        Resultado do teste de conectividade.
    """
    result = get_container().context_service.test_minio_config(
        endpoint=payload.endpoint,
        access_key=payload.access_key,
        secret_key=payload.secret_key,
        secure=payload.secure,
    )
    return ConnectionTestResponse(success=result.success, message=result.message)


@router.get("/database", response_model=DatabaseConfigResponse)
def get_database_config() -> DatabaseConfigResponse:
    """Retorna a conexão do SQL Server de destino da carga de tabelas, sem expor a senha.

    Returns:
        Campos da conexão salva e se a senha já está configurada.
    """
    return DatabaseConfigResponse(**get_container().system_settings_service.get_database_config_for_display())


@router.put("/database", response_model=DatabaseConfigResponse)
def update_database_config(payload: DatabaseConfigRequest) -> DatabaseConfigResponse:
    """Salva a conexão do SQL Server de destino, usada por todos os contexts com carga no banco ligada.

    Args:
        payload: Servidor, porta, banco, usuário e senha (em branco mantém a salva).

    Returns:
        Conexão já atualizada, sem a senha.

    Raises:
        HTTPException: 422 se não houver senha informada nem uma já salva.
    """
    service = get_container().system_settings_service
    try:
        service.update_database_config(
            host=payload.host,
            port=payload.port,
            database=payload.database,
            username=payload.username,
            password=payload.password,
        )
    except DatabaseConfigIncompleteError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"field": "password", "message": str(error)}
        ) from error
    return DatabaseConfigResponse(**service.get_database_config_for_display())


@router.delete("/database", status_code=status.HTTP_204_NO_CONTENT)
def clear_database_config() -> None:
    """Remove a conexão do SQL Server de destino."""
    get_container().system_settings_service.clear_database_config()


@router.post("/database/test", response_model=ConnectionTestResponse)
def test_database_config(payload: DatabaseConfigRequest) -> ConnectionTestResponse:
    """Testa a conexão com o SQL Server (`SELECT 1`) usando os valores do formulário, antes de salvar.

    Args:
        payload: Servidor, porta, banco, usuário e senha (em branco usa a salva).

    Returns:
        Resultado do teste de conectividade.
    """
    try:
        config = get_container().system_settings_service.resolve_database_config(
            host=payload.host,
            port=payload.port,
            database=payload.database,
            username=payload.username,
            password=payload.password,
        )
        check_database_connection(config.to_url())
    except Exception as error:  # noqa: BLE001 - erro de conectividade externo, reportado ao admin
        return ConnectionTestResponse(success=False, message=f"Falha ao conectar no banco: {error}")
    return ConnectionTestResponse(success=True, message=f"Conectado com sucesso em {payload.host}/{payload.database}.")
