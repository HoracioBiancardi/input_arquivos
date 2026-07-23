"""Writer de destino que envia artefatos para uma tabela em um banco de dados relacional (ex.: SQL Server)."""

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Inspector
from sqlalchemy.types import Text

from app.destinations.base import DestinationWriter, WriteResult
from app.ingestion.pipeline import IngestResult
from app.models.context import Context, WriteMode


class SchemaMismatchError(ValueError):
    """Erro levantado quando as colunas do arquivo enviado não correspondem às da tabela existente."""


class SqlServerWriter(DestinationWriter):
    """Envia o DataFrame de um artefato para uma tabela de banco de dados relacional.

    A lógica de append/create é feita explicitamente (em vez de depender do
    `if_exists="replace"` do pandas, que apaga e recria a tabela de forma
    destrutiva): "append" grava na tabela existente após validar as colunas;
    "create_new" nunca substitui uma tabela já existente, criando uma versão
    com sufixo de timestamp quando necessário.
    """

    def write(self, artifact: IngestResult, context: Context, write_mode: WriteMode | None) -> WriteResult:
        """Grava o DataFrame do artefato na tabela configurada no contexto.

        Args:
            artifact: Artefato produzido pelo `IngestionPipeline`. Deve conter
                um `dataframe` (não se aplica a PDFs em modo raw_archive).
            context: Contexto de destino; deve ter `db_connection_string`,
                `db_schema_name` e `db_table` preenchidos.
            write_mode: Modo de escrita desejado (append ou create_new).

        Returns:
            Resultado da escrita, contendo o nome real da tabela usada
            (pode diferir de `context.db_table` em `create_new` com versionamento).

        Raises:
            ValueError: Se o contexto não tiver conexão/tabela configuradas, ou
                se o artefato não tiver um DataFrame associado.
            SchemaMismatchError: Se `write_mode` for append e as colunas do
                arquivo enviado não corresponderem às da tabela existente.
        """
        if artifact.dataframe is None:
            raise ValueError("Este artefato não possui um DataFrame para gravar em banco de dados.")
        if not context.db_connection_string or not context.db_table:
            raise ValueError(f"Context '{context.name}' não possui conexão/tabela de banco de dados configuradas.")

        effective_write_mode = write_mode or context.default_write_mode
        engine = create_engine(context.db_connection_string)
        inspector = inspect(engine)
        table_exists = inspector.has_table(context.db_table, schema=context.db_schema_name)

        if effective_write_mode == WriteMode.APPEND:
            target_table = context.db_table
            if table_exists:
                self._validate_column_compatibility(inspector, target_table, context.db_schema_name, artifact.dataframe)
                pandas_if_exists = "append"
            else:
                pandas_if_exists = "fail"
        else:
            if table_exists:
                target_table = self._versioned_table_name(context.db_table)
            else:
                target_table = context.db_table
            pandas_if_exists = "fail"

        dtype_overrides = {"text_content": Text} if "text_content" in artifact.dataframe.columns else None
        artifact.dataframe.to_sql(
            target_table,
            engine,
            schema=context.db_schema_name,
            if_exists=pandas_if_exists,
            index=False,
            dtype=dtype_overrides,
        )
        return WriteResult(
            destination_detail=f"{context.db_schema_name}.{target_table}",
            row_count=len(artifact.dataframe),
        )

    def _validate_column_compatibility(
        self, inspector: Inspector, table_name: str, schema_name: str, dataframe: pd.DataFrame
    ) -> None:
        """Confere se as colunas do DataFrame batem com as colunas da tabela existente.

        Args:
            inspector: `Inspector` do SQLAlchemy sobre o engine de destino.
            table_name: Nome da tabela existente.
            schema_name: Schema da tabela existente.
            dataframe: DataFrame a ser gravado.

        Raises:
            SchemaMismatchError: Se houver colunas no DataFrame ausentes na
                tabela existente (schema incompatível para append).
        """
        existing_columns = {column["name"] for column in inspector.get_columns(table_name, schema=schema_name)}
        incoming_columns = set(dataframe.columns)
        missing_in_table = incoming_columns - existing_columns
        if missing_in_table:
            raise SchemaMismatchError(
                f"As colunas {sorted(missing_in_table)} do arquivo enviado não existem na tabela "
                f"'{schema_name}.{table_name}'. Não é possível fazer append com um schema incompatível."
            )

    def _versioned_table_name(self, base_table_name: str) -> str:
        """Gera um nome de tabela versionado para não sobrescrever uma tabela já existente.

        Args:
            base_table_name: Nome de tabela originalmente solicitado.

        Returns:
            Nome de tabela no formato `{base_table_name}_{yyyyMMddHHmmss}`.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"{base_table_name}_{timestamp}"
