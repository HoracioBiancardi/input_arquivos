"""Writer de destino que salva artefatos em uma pasta no disco local.

Existe para permitir testar o sistema por completo (upload -> conversão ->
persistência) sem depender de um MinIO ou SQL Server externos: um context
configurado com `destination_type=local` grava o Parquet (ou o PDF bruto, em
modo raw_archive) direto numa pasta local, com a mesma estrutura de
particionamento por data usada no MinIO.
"""

from pathlib import Path

from app.destinations.base import DestinationWriter, WriteResult
from app.destinations.key_builder import PartitionedKeyBuilder
from app.ingestion.pipeline import IngestResult
from app.models.context import Context, WriteMode


class LocalFileWriter(DestinationWriter):
    """Salva artefatos (Parquet ou PDF bruto) em uma pasta no disco local configurada no contexto."""

    def __init__(self) -> None:
        """Inicializa o writer local."""
        self._key_builder = PartitionedKeyBuilder()

    def write(self, artifact: IngestResult, context: Context, write_mode: WriteMode | None) -> WriteResult:
        """Grava o artefato em um arquivo dentro da pasta local do contexto.

        Args:
            artifact: Artefato produzido pelo `IngestionPipeline`.
            context: Contexto de destino. Se `local_path` não for informado,
                os arquivos são salvos a partir da raiz do projeto.
            write_mode: Ignorado neste writer (não se aplica a arquivos em disco).

        Returns:
            Resultado da escrita, contendo o caminho absoluto do arquivo criado.
        """
        root_path = context.local_path or "."
        relative_key = self._key_builder.build(context.name, artifact.suggested_filename)
        destination_path = Path(root_path, *relative_key.split("/")).resolve()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        destination_path.write_bytes(artifact.artifact_bytes)

        return WriteResult(destination_detail=str(destination_path), row_count=artifact.row_count)
