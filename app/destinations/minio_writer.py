"""Writer de destino que envia artefatos para um bucket no servidor MinIO."""

import io

from minio import Minio

from app.config import get_settings
from app.destinations.base import DestinationWriter, WriteResult
from app.destinations.key_builder import PartitionedKeyBuilder
from app.ingestion.pipeline import IngestResult
from app.models.context import Context, WriteMode


class MinioWriter(DestinationWriter):
    """Envia artefatos (Parquet ou PDF bruto) para o bucket MinIO configurado no contexto."""

    def __init__(self, client: Minio | None = None) -> None:
        """Inicializa o writer MinIO.

        Args:
            client: Cliente `Minio` a usar. Se `None`, um cliente é criado a
                partir das configurações globais da aplicação (endpoint e
                credenciais são compartilhados por todos os contexts).
        """
        if client is not None:
            self._client = client
        else:
            settings = get_settings()
            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
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

        if not self._client.bucket_exists(context.minio_bucket):
            self._client.make_bucket(context.minio_bucket)

        object_key = self._key_builder.build(context.name, artifact.suggested_filename)
        data = io.BytesIO(artifact.artifact_bytes)
        self._client.put_object(
            bucket_name=context.minio_bucket,
            object_name=object_key,
            data=data,
            length=len(artifact.artifact_bytes),
        )
        return WriteResult(destination_detail=f"{context.minio_bucket}/{object_key}", row_count=artifact.row_count)
