"""Contrato comum a todo destination writer (MinIO, SQL Server, ou destinos futuros)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.ingestion.pipeline import IngestResult
from app.models.context import Context, WriteMode


@dataclass
class WriteResult:
    """Resultado da escrita de um artefato em um destino.

    Attributes:
        destination_detail: Descrição do local final dos dados (ex.: chave do
            objeto no MinIO, ou "schema.tabela" no SQL Server).
        row_count: Quantidade de linhas efetivamente gravadas, quando aplicável.
    """

    destination_detail: str
    row_count: int | None


class DestinationWriter(ABC):
    """Contrato implementado por todo writer capaz de enviar um `IngestResult` a um destino."""

    @abstractmethod
    def write(self, artifact: IngestResult, context: Context, write_mode: WriteMode | None) -> WriteResult:
        """Envia o artefato de ingestão para o destino configurado no contexto.

        Args:
            artifact: Artefato produzido pelo `IngestionPipeline`.
            context: Contexto que define os detalhes do destino (bucket, tabela, etc.).
            write_mode: Modo de escrita (append/create_new), relevante apenas
                para destinos de banco de dados.

        Returns:
            Resultado da escrita, usado para preencher o audit log.
        """
        raise NotImplementedError
