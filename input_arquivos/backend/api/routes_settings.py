"""Rotas da API REST para a configuração global do MinIO (admin-only)."""

from fastapi import APIRouter, Depends, HTTPException, status

from input_arquivos.backend.auth.dependencies import require_admin
from input_arquivos.backend.schemas.context import ConnectionTestResponse
from input_arquivos.backend.schemas.system_settings import (
    MinioConfigResponse,
    MinioConfigTestRequest,
    MinioConfigUpdateRequest,
)
from input_arquivos.backend.services.container import get_container
from input_arquivos.backend.services.system_settings_service import MinioConfigIncompleteError

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
