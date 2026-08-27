"""Construção do cliente MinIO compartilhado pelo writer e pelo serviço de preview."""

from minio import Minio

from input_arquivos.backend.db.session import get_session_factory
from input_arquivos.backend.services.system_settings_service import MinioConfig, SystemSettingsService


def resolve_minio_config() -> MinioConfig:
    """Resolve a configuração do MinIO a usar: a salva pelo admin em `/admin/settings`, ou o `.env` como fallback.

    Returns:
        Configuração do MinIO já resolvida.
    """
    return SystemSettingsService(get_session_factory()).get_minio_config()


def build_minio_client(config: MinioConfig | None = None) -> Minio:
    """Cria um cliente `Minio` a partir da configuração global do MinIO.

    Endpoint e credenciais são compartilhados por todos os contexts do tipo
    MinIO; só o bucket varia por context. A configuração é resolvida a cada
    chamada (não cacheada), para que uma configuração alterada pelo admin
    valha na próxima escrita, sem precisar reiniciar o servidor.

    Args:
        config: Configuração já resolvida a usar. Se `None`, é resolvida
            agora via `resolve_minio_config()`.

    Returns:
        Cliente `Minio` pronto para uso.
    """
    resolved = config if config is not None else resolve_minio_config()
    return Minio(
        resolved.endpoint,
        access_key=resolved.access_key,
        secret_key=resolved.secret_key,
        secure=resolved.secure,
    )
