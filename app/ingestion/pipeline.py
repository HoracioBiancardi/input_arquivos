"""Orquestração do pipeline de ingestão: detecta o tipo de arquivo, lê, transforma e gera o artefato final."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.ingestion.file_types import FileType, FileTypeRegistry
from app.ingestion.parquet import ParquetConverter
from app.ingestion.readers import CsvReader, ExcelReader, PdfMetadataReader, PdfTableReader
from app.models.context import Context, PdfMode


@dataclass
class IngestResult:
    """Artefato produzido pelo pipeline de ingestão, pronto para um destination writer.

    Attributes:
        artifact_bytes: Conteúdo binário final (Parquet, ou PDF bruto em modo raw_archive).
        artifact_kind: Tipo do artefato ("parquet" ou "raw_pdf").
        dataframe: DataFrame gerado, quando `artifact_kind` é "parquet"
            (usado pelos writers de banco de dados). `None` em modo raw_archive.
        row_count: Quantidade de linhas do DataFrame, quando aplicável.
        page_count: Quantidade de páginas do PDF de origem, quando aplicável.
        suggested_filename: Nome de arquivo sugerido para o artefato final.
    """

    artifact_bytes: bytes
    artifact_kind: str
    dataframe: pd.DataFrame | None
    row_count: int | None
    page_count: int | None
    suggested_filename: str


class UnsupportedFileTypeError(ValueError):
    """Erro levantado quando a extensão do arquivo enviado não é reconhecida pelo sistema."""


class FileTypeNotAllowedError(ValueError):
    """Erro levantado quando o tipo do arquivo enviado não está entre os permitidos pelo contexto."""


class IngestionPipeline:
    """Detecta o tipo de um arquivo enviado, lê seu conteúdo e produz o artefato final para o destino."""

    def __init__(self) -> None:
        """Inicializa o pipeline com os leitores, o conversor Parquet e o registro de tipos de arquivo."""
        self._excel_reader = ExcelReader()
        self._csv_reader = CsvReader()
        self._pdf_table_reader = PdfTableReader()
        self._pdf_metadata_reader = PdfMetadataReader()
        self._parquet_converter = ParquetConverter()
        self._file_types = FileTypeRegistry()

    def process(self, file_bytes: bytes, filename: str, context: Context, uploaded_by: str) -> IngestResult:
        """Processa um arquivo enviado de acordo com sua extensão e o contexto selecionado.

        Args:
            file_bytes: Conteúdo bruto do arquivo enviado.
            filename: Nome original do arquivo.
            context: Contexto selecionado pelo usuário, que determina os tipos de
                arquivo aceitos (`context.allowed_file_types`), o comportamento de
                PDFs (`context.pdf_mode`) e o destino final.
            uploaded_by: Nome do usuário autenticado que realizou o upload.

        Returns:
            O artefato pronto para ser entregue ao destination writer do contexto.

        Raises:
            UnsupportedFileTypeError: Se a extensão do arquivo não for reconhecida.
            FileTypeNotAllowedError: Se o tipo do arquivo não estiver entre os
                tipos permitidos configurados para o contexto.
        """
        extension = Path(filename).suffix.lower()
        file_type = self._file_types.type_for_extension(extension)
        if file_type is None:
            raise UnsupportedFileTypeError(f"Tipo de arquivo não suportado: '{extension}'.")

        allowed_types = self._file_types.deserialize(context.allowed_file_types)
        if file_type not in allowed_types:
            allowed_labels = ", ".join(allowed.value for allowed in allowed_types)
            raise FileTypeNotAllowedError(
                f"O contexto '{context.name}' só aceita: {allowed_labels}. "
                f"Arquivos do tipo '{file_type.value}' não são permitidos aqui."
            )

        if file_type == FileType.PDF and context.pdf_mode == PdfMode.RAW_ARCHIVE:
            return IngestResult(
                artifact_bytes=file_bytes,
                artifact_kind="raw_pdf",
                dataframe=None,
                row_count=None,
                page_count=None,
                suggested_filename=filename,
            )

        dataframe = self._read(file_bytes, filename, file_type, context)
        dataframe = self._inject_tracking_columns(dataframe, context.name, uploaded_by)
        parquet_bytes = self._parquet_converter.to_bytes(dataframe)
        page_count = int(dataframe["page_count"].iloc[0]) if "page_count" in dataframe.columns else None

        return IngestResult(
            artifact_bytes=parquet_bytes,
            artifact_kind="parquet",
            dataframe=dataframe,
            row_count=len(dataframe),
            page_count=page_count,
            suggested_filename=f"{Path(filename).stem}.parquet",
        )

    def _read(self, file_bytes: bytes, filename: str, file_type: FileType, context: Context) -> pd.DataFrame:
        """Despacha a leitura do arquivo para o leitor apropriado, conforme o tipo e o contexto.

        Args:
            file_bytes: Conteúdo bruto do arquivo enviado.
            filename: Nome original do arquivo.
            file_type: Tipo lógico do arquivo, já validado contra o contexto.
            context: Contexto selecionado, usado para decidir o modo de leitura de PDFs.

        Returns:
            DataFrame com os dados extraídos do arquivo.
        """
        if file_type == FileType.EXCEL:
            return self._excel_reader.read(file_bytes)
        if file_type == FileType.CSV:
            return self._csv_reader.read(file_bytes)
        if context.pdf_mode == PdfMode.EXTRACT_TABLES:
            return self._pdf_table_reader.read(file_bytes)
        return self._pdf_metadata_reader.read(file_bytes, filename)

    def _inject_tracking_columns(self, dataframe: pd.DataFrame, context_name: str, uploaded_by: str) -> pd.DataFrame:
        """Insere as colunas de rastreabilidade como as três primeiras colunas do DataFrame.

        Args:
            dataframe: DataFrame original extraído do arquivo.
            context_name: Nome do contexto usado no upload.
            uploaded_by: Nome do usuário autenticado que realizou o upload.

        Returns:
            Novo DataFrame com `data_envio`, `contexto` e `enviado_por` como
            as três primeiras colunas.
        """
        tracked = dataframe.copy()
        tracked.insert(0, "enviado_por", uploaded_by)
        tracked.insert(0, "contexto", context_name)
        tracked.insert(0, "data_envio", datetime.now(timezone.utc))
        return tracked
