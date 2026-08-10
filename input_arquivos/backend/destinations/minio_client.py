"""Construção do cliente MinIO compartilhado pelo writer e pelo serviço de preview."""

from minio import Minio

from input_arquivos.backend.config import get_settings


def build_minio_client() -> Minio:
    """Cria um cliente `Minio` a partir das configurações globais da aplicação.

    Endpoint e credenciais são compartilhados por todos os contexts do tipo
    MinIO; só o bucket varia por context.

    Returns:
        Cliente `Minio` pronto para uso.
    """
    settings = get_settings()
    return Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
