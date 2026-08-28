"""Contrato comum a todo destination writer (MinIO, pasta local, ou destinos futuros)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from input_arquivos.backend.ingestion.pipeline import IngestResult
from input_arquivos.backend.models.context import Context


@dataclass
class WriteResult:
    """Resultado da escrita de um artefato em um destino.

    Attributes:
        destination_detail: Descrição do local final dos dados (ex.: chave do
            objeto no MinIO, ou caminho do arquivo local).
        row_count: Quantidade de linhas efetivamente gravadas, quando aplicável.
    """

    destination_detail: str
    row_count: int | None


class DestinationWriter(ABC):
    """Contrato implementado por todo writer capaz de enviar um `IngestResult` a um destino."""

    @abstractmethod
    def write(self, artifact: IngestResult, context: Context) -> WriteResult:
        """Envia o artefato de ingestão para o destino configurado no contexto.

        Args:
            artifact: Artefato produzido pelo `IngestionPipeline`.
            context: Contexto que define os detalhes do destino (bucket, pasta, etc.).

        Returns:
            Resultado da escrita, usado para preencher o audit log.
        """
        raise NotImplementedError
