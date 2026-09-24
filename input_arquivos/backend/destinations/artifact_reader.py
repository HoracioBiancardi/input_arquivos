"""Leitura de volta, a partir do destino, do artefato gravado por um upload."""

from pathlib import Path

from input_arquivos.backend.destinations.minio_client import build_minio_client
from input_arquivos.backend.models.context import DestinationType
from input_arquivos.backend.models.upload_history import UploadHistory


def read_artifact_bytes(history: UploadHistory) -> bytes:
    """Lê o conteúdo do artefato gravado por um upload, no MinIO ou na pasta local.

    Usado pela tela de visualização e pela recarga de um upload no banco de
    dados de destino — o MinIO (ou a pasta local) é a fonte da verdade.

    Args:
        history: Registro do upload bem-sucedido; `destination_detail` é o
            caminho local ou `bucket/chave` no MinIO.

    Returns:
        Conteúdo bruto do artefato.
    """
    if history.destination_type == DestinationType.LOCAL:
        return Path(history.destination_detail).read_bytes()

    bucket, key = history.destination_detail.split("/", 1)
    client = build_minio_client()
    response = client.get_object(bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()
