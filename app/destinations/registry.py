"""Registro de destination writers disponíveis, indexados por tipo de destino."""

from app.destinations.base import DestinationWriter
from app.destinations.local_writer import LocalFileWriter
from app.destinations.minio_writer import MinioWriter
from app.destinations.sqlserver_writer import SqlServerWriter
from app.models.context import DestinationType


class DestinationWriterRegistry:
    """Resolve o destination writer apropriado para um `DestinationType`.

    Centraliza o mapeamento tipo-de-destino -> writer, de modo que adicionar
    um novo destino no futuro (ex.: Postgres, outro provedor S3) exija apenas
    implementar um novo `DestinationWriter` e registrá-lo aqui.
    """

    def __init__(self) -> None:
        """Inicializa o registro com os writers padrão da aplicação."""
        self._writers: dict[DestinationType, DestinationWriter] = {
            DestinationType.MINIO: MinioWriter(),
            DestinationType.SQLSERVER: SqlServerWriter(),
            DestinationType.LOCAL: LocalFileWriter(),
        }

    def get(self, destination_type: DestinationType) -> DestinationWriter:
        """Retorna o writer registrado para o tipo de destino informado.

        Args:
            destination_type: Tipo de destino do contexto (MinIO, SQL Server ou pasta local).

        Returns:
            Instância do `DestinationWriter` correspondente.

        Raises:
            ValueError: Se não houver writer registrado para o tipo informado.
        """
        writer = self._writers.get(destination_type)
        if writer is None:
            raise ValueError(f"Nenhum destination writer registrado para '{destination_type}'.")
        return writer
