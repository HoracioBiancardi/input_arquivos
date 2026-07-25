"""Serviço que reconstrói a tabela gerada por um upload, para exibição na tela de visualização."""

import io
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, select

from app.backend.db.session import DatabaseSessionFactory
from app.backend.destinations.minio_client import build_minio_client
from app.backend.models.context import DestinationType
from app.backend.models.upload_history import UploadHistory, UploadStatus
from app.backend.services.context_service import ContextService


class UploadNotFoundError(ValueError):
    """Erro levantado quando o `UploadHistory` informado não existe."""


class PreviewNotAvailableError(ValueError):
    """Erro levantado quando o upload não gerou uma tabela para visualizar."""


@dataclass
class TablePreview:
    """Recorte da tabela gerada por um upload, pronto para exibição.

    Attributes:
        filename: Nome original do arquivo enviado.
        context_name: Nome do contexto usado no upload.
        columns: Nomes das colunas da tabela.
        rows: Linhas da tabela (até `limit`), cada uma como lista de valores
            na mesma ordem de `columns`. Valores ausentes (NaN/NaT) já vêm
            convertidos para `None`.
        total_row_count: Quantidade de linhas geradas por este upload.
        truncated: Se `rows` contém menos linhas do que `total_row_count`.
    """

    filename: str
    context_name: str
    columns: list[str]
    rows: list[list[object]]
    total_row_count: int | None
    truncated: bool


class PreviewService:
    """Reconstrói o DataFrame gerado por um upload, lendo de volta do destino onde foi gravado."""

    def __init__(self, session_factory: DatabaseSessionFactory, context_service: ContextService) -> None:
        """Inicializa o serviço de preview.

        Args:
            session_factory: Fábrica de sessões do banco de configuração local.
            context_service: Serviço usado para buscar o context (necessário
                para obter a connection string em previews de SQL Server).
        """
        self._session_factory = session_factory
        self._context_service = context_service

    def get_preview(self, upload_id: int, limit: int = 200) -> TablePreview:
        """Monta um recorte da tabela gerada por um upload.

        Args:
            upload_id: Identificador do `UploadHistory`.
            limit: Quantidade máxima de linhas a retornar.

        Returns:
            Recorte da tabela, pronto para serialização.

        Raises:
            UploadNotFoundError: Se não existir um `UploadHistory` com esse id.
            PreviewNotAvailableError: Se o upload não tiver sido bem-sucedido,
                ou não tiver gerado uma tabela (ex.: PDF/imagem em modo
                raw_archive).
        """
        history = self._get_history(upload_id)
        if history.status != UploadStatus.SUCCESS or history.artifact_kind != "parquet":
            raise PreviewNotAvailableError("Este envio não gerou uma tabela para visualizar.")

        dataframe = self._read_dataframe(history, limit)
        preview_df = dataframe.head(limit)
        sanitized = preview_df.astype(object).where(pd.notna(preview_df), None)

        return TablePreview(
            filename=history.filename,
            context_name=history.context_name,
            columns=[str(column) for column in dataframe.columns],
            rows=sanitized.values.tolist(),
            total_row_count=history.row_count,
            truncated=(history.row_count or 0) > limit,
        )

    def _get_history(self, upload_id: int) -> UploadHistory:
        """Busca um `UploadHistory` pelo id.

        Args:
            upload_id: Identificador do registro.

        Returns:
            O registro encontrado.

        Raises:
            UploadNotFoundError: Se não existir um registro com esse id.
        """
        with self._session_factory.session() as db_session:
            history = db_session.get(UploadHistory, upload_id)
            if history is None:
                raise UploadNotFoundError(f"Upload '{upload_id}' não encontrado.")
            db_session.expunge(history)
            return history

    def _read_dataframe(self, history: UploadHistory, limit: int) -> pd.DataFrame:
        """Lê de volta o DataFrame gravado por um upload, a partir do seu destino.

        Args:
            history: Registro do upload, já confirmado como tendo gerado um Parquet.
            limit: Quantidade máxima de linhas a ler (só é aplicado na origem
                para o destino SQL Server, para não puxar a tabela inteira).

        Returns:
            DataFrame lido de volta do destino.

        Raises:
            PreviewNotAvailableError: Se o context original não existir mais
                (necessário para reconstruir a conexão com SQL Server).
        """
        if history.destination_type == DestinationType.LOCAL:
            return pd.read_parquet(history.destination_detail)

        if history.destination_type == DestinationType.MINIO:
            bucket, key = history.destination_detail.split("/", 1)
            client = build_minio_client()
            response = client.get_object(bucket, key)
            try:
                data = response.read()
            finally:
                response.close()
                response.release_conn()
            return pd.read_parquet(io.BytesIO(data))

        context = self._context_service.get_by_name(history.context_name)
        if context is None or not context.db_connection_string:
            raise PreviewNotAvailableError(
                f"O contexto '{history.context_name}' não existe mais ou não tem conexão de banco "
                "configurada — não é possível reconstruir a tabela."
            )
        schema_name, table_name = history.destination_detail.split(".", 1)
        engine = create_engine(context.db_connection_string)
        table = Table(table_name, MetaData(), autoload_with=engine, schema=schema_name)
        return pd.read_sql(select(table).limit(limit), engine)
