"""Writer de destino que envia artefatos para um bucket no servidor MinIO."""

import io

from minio import Minio

from input_arquivos.backend.destinations.base import DestinationWriter, WriteResult
from input_arquivos.backend.destinations.key_builder import PartitionedKeyBuilder
from input_arquivos.backend.destinations.minio_client import build_minio_client
from input_arquivos.backend.ingestion.pipeline import IngestResult
from input_arquivos.backend.models.context import Context, WriteMode


class MinioWriter(DestinationWriter):
    """Envia artefatos (Parquet ou PDF bruto) para o bucket MinIO configurado no contexto."""

    def __init__(self, client: Minio | None = None) -> None:
        """Inicializa o writer MinIO.

        Args:
            client: Cliente `Minio` a usar em toda escrita. Se `None`
                (padrão), um cliente é criado sob demanda a cada `write()` a
                partir da configuração global mais atual (admin, com
                fallback pro `.env`) — não cacheado na construção, para que
                uma configuração alterada pelo admin em `/admin/settings`
                valha na próxima escrita sem reiniciar o servidor.
        """
        self._client_override = client
        self._key_builder = PartitionedKeyBuilder()

    def write(self, artifact: IngestResult, context: Context, write_mode: WriteMode | None) -> WriteResult:
        """Faz upload do artefato para o bucket do contexto, sob uma chave particionada por data.

        Args:
            artifact: Artefato produzido pelo `IngestionPipeline`.
            context: Contexto de destino; deve ter `minio_bucket` preenchido.
            write_mode: Ignorado neste writer (não se aplica a armazenamento de objetos).

        Returns:
            Resultado da escrita, contendo a chave do objeto criado no bucket.

        Raises:
            ValueError: Se o contexto não tiver um bucket MinIO configurado.
        """
        if not context.minio_bucket:
            raise ValueError(f"Context '{context.name}' não possui um bucket MinIO configurado.")

        client = self._client_override if self._client_override is not None else build_minio_client()
        if not client.bucket_exists(context.minio_bucket):
            client.make_bucket(context.minio_bucket)

        object_key = self._key_builder.build(context.name, artifact.suggested_filename)
        data = io.BytesIO(artifact.artifact_bytes)
        client.put_object(
            bucket_name=context.minio_bucket,
            object_name=object_key,
            data=data,
            length=len(artifact.artifact_bytes),
        )
        return WriteResult(destination_detail=f"{context.minio_bucket}/{object_key}", row_count=artifact.row_count)
