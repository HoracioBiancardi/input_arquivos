"""Carga do Parquet de um upload como linhas na tabela do contexto, no banco de dados de destino (ex.: SQL Server)."""

import io
from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd
from sqlalchemy import MetaData, Table, create_engine, delete, inspect, text
from sqlalchemy.dialects import mssql
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.pool import NullPool
from sqlalchemy.types import BigInteger, Boolean, Date, DateTime, Float, TypeEngine, UnicodeText

from input_arquivos.backend.destinations.key_builder import slugify
from input_arquivos.backend.models.context import Context, LoadMode

UPLOAD_ID_COLUMN = "id_envio"
# Tempo máximo (s) para abrir a conexão com o SQL Server — o padrão do pymssql (60s)
# deixaria o "Testar conexão" e a carga presos com um servidor inalcançável.
_LOGIN_TIMEOUT_SECONDS = 10

# Tipos fixados para o SQL Server: sem a versão do servidor, o dialeto mssql cai nos
# tipos legados (`NTEXT` para texto, `DATETIME` para data) — aqui vale sempre o moderno.
_TEXT_TYPE = UnicodeText().with_variant(mssql.NVARCHAR(), "mssql")
_DATE_TYPE = Date().with_variant(mssql.DATE(), "mssql")
_DATETIME_TYPE = DateTime().with_variant(mssql.DATETIME2(), "mssql")


class DatabaseNotConfiguredError(ValueError):
    """Erro levantado quando um contexto pede carga no banco mas a conexão global não foi configurada."""


class TableSchemaMismatchError(ValueError):
    """Erro levantado quando o arquivo traz colunas que a tabela já existente no banco não tem."""


@dataclass
class LoadResult:
    """Resultado da carga de um upload no banco de dados de destino.

    Attributes:
        table: Tabela de destino, como `schema.tabela` (ou só `tabela`, no schema padrão).
        row_count: Quantidade de linhas inseridas.
    """

    table: str
    row_count: int


def target_table_name(context: Context) -> str:
    """Resolve o nome da tabela de destino de um contexto.

    Args:
        context: Contexto do upload.

    Returns:
        `context.db_table`, ou o slug do nome do contexto (o mesmo da pasta
        no MinIO) quando a tabela não foi informada.
    """
    return context.db_table or slugify(context.name)


def describe_target_table(context: Context) -> str:
    """Monta a descrição `schema.tabela` da tabela de destino de um contexto, para exibição.

    Args:
        context: Contexto do upload.

    Returns:
        `schema.tabela`, ou só `tabela` quando o schema padrão da conexão é usado.
    """
    table_name = target_table_name(context)
    return f"{context.db_schema}.{table_name}" if context.db_schema else table_name


def create_target_engine(database_url: URL | str) -> Engine:
    """Cria um engine sem pool para o banco de destino (uma conexão por carga/teste).

    Args:
        database_url: URL SQLAlchemy do banco de destino.

    Returns:
        Engine pronto para uso; o chamador deve chamar `dispose()` ao terminar.
    """
    url = make_url(database_url)
    connect_args = {"login_timeout": _LOGIN_TIMEOUT_SECONDS} if url.get_backend_name() == "mssql" else {}
    return create_engine(url, poolclass=NullPool, connect_args=connect_args)


def check_database_connection(database_url: URL | str) -> str:
    """Abre uma conexão com o banco de destino e executa `SELECT 1`.

    Args:
        database_url: URL SQLAlchemy do banco a testar.

    Returns:
        Nome do dialeto conectado (ex.: `mssql`), para a mensagem de sucesso.

    Raises:
        Exception: Qualquer erro do driver ao conectar/consultar.
    """
    engine = create_target_engine(database_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return engine.dialect.name
    finally:
        engine.dispose()


class DatabaseLoader:
    """Insere o Parquet de um upload na tabela do contexto, criando a tabela no primeiro upload.

    Cada linha ganha a coluna `id_envio` (id do `UploadHistory`). No modo
    APPEND, as linhas do mesmo `id_envio` são apagadas antes de inserir, na
    mesma transação — recarregar um upload nunca duplica linhas. No modo
    REPLACE, todo o conteúdo da tabela é apagado antes (via `DELETE`, não
    `DROP`: permissões e índices criados na tabela pelo time de banco são
    preservados).
    """

    def __init__(self, url_provider: Callable[[], URL | str | None]) -> None:
        """Inicializa o loader.

        Args:
            url_provider: Função que devolve a URL SQLAlchemy do banco de
                destino (ou `None` se não configurada). Resolvida a cada carga,
                para que uma alteração em `/admin/settings` valha sem reiniciar.
        """
        self._url_provider = url_provider

    def load(self, parquet_bytes: bytes, context: Context, upload_id: int) -> LoadResult:
        """Carrega o Parquet de um upload na tabela do contexto.

        Args:
            parquet_bytes: Conteúdo do Parquet gravado no MinIO/pasta local.
            context: Contexto do upload (tabela, schema e modo de carga).
            upload_id: Id do `UploadHistory`, gravado na coluna `id_envio`.

        Returns:
            Tabela de destino e quantidade de linhas inseridas.

        Raises:
            DatabaseNotConfiguredError: Se a conexão global não estiver configurada.
            TableSchemaMismatchError: Se a tabela já existir sem alguma coluna
                do arquivo, ou sem a coluna `id_envio`.
        """
        database_url = self._url_provider()
        if not database_url:
            raise DatabaseNotConfiguredError(
                "Banco de dados de destino não configurado. Configure a conexão em Admin → Configurações."
            )

        dataframe = pd.read_parquet(io.BytesIO(parquet_bytes))
        dataframe.insert(0, UPLOAD_ID_COLUMN, upload_id)
        dataframe = self._to_naive_utc(dataframe)
        table_name = target_table_name(context)
        schema = context.db_schema or None

        engine = create_target_engine(database_url)
        try:
            with engine.begin() as connection:
                if inspect(connection).has_table(table_name, schema=schema):
                    table = Table(table_name, MetaData(), schema=schema, autoload_with=connection)
                    self._check_columns(table, dataframe, describe_target_table(context))
                    if (context.load_mode or LoadMode.APPEND) == LoadMode.REPLACE:
                        connection.execute(delete(table))
                    else:
                        upload_id_column = next(
                            column for column in table.columns if column.name.casefold() == UPLOAD_ID_COLUMN
                        )
                        connection.execute(delete(table).where(upload_id_column == upload_id))
                dataframe.to_sql(
                    table_name,
                    connection,
                    schema=schema,
                    if_exists="append",
                    index=False,
                    dtype=self._sql_types(dataframe),
                    chunksize=1000,
                )
        finally:
            engine.dispose()

        return LoadResult(table=describe_target_table(context), row_count=len(dataframe))

    def _check_columns(self, table: Table, dataframe: pd.DataFrame, table_label: str) -> None:
        """Confere se a tabela existente comporta todas as colunas do arquivo.

        Colunas da tabela ausentes no arquivo não são erro (ficam nulas).
        A comparação ignora maiúsculas/minúsculas, como a collation padrão do SQL Server.

        Raises:
            TableSchemaMismatchError: Se faltar na tabela alguma coluna do arquivo.
        """
        existing = {column.name.casefold() for column in table.columns}
        if UPLOAD_ID_COLUMN not in existing:
            raise TableSchemaMismatchError(
                f"A tabela '{table_label}' já existe e não tem a coluna '{UPLOAD_ID_COLUMN}' — "
                "ela não foi criada por este sistema. Escolha outra tabela no contexto."
            )
        missing = [str(column) for column in dataframe.columns if str(column).casefold() not in existing]
        if missing:
            raise TableSchemaMismatchError(
                f"A tabela '{table_label}' não tem as colunas {', '.join(missing)}, que vieram neste arquivo. "
                "Adicione essas colunas na tabela (ALTER TABLE) e recarregue o envio pelo Audit Log."
            )

    def _to_naive_utc(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        """Converte colunas de data/hora com fuso (ex.: `data_envio`) para UTC sem fuso.

        O driver do SQL Server não grava `datetime` com fuso de forma
        consistente; como `data_envio` já é gerada em UTC, gravar como
        `DATETIME2` em UTC evita a ambiguidade.
        """
        converted = dataframe.copy()
        for column in converted.columns:
            if isinstance(converted[column].dtype, pd.DatetimeTZDtype):
                converted[column] = converted[column].dt.tz_convert("UTC").dt.tz_localize(None)
        return converted

    def _sql_types(self, dataframe: pd.DataFrame) -> dict[str, TypeEngine]:
        """Define o tipo SQL de cada coluna, usado quando a tabela é criada.

        Texto vira `NVARCHAR(MAX)` no SQL Server: sem isso o pandas criaria
        `VARCHAR`, que perde acentos fora da collation do banco. Data vira
        `DATE` e data/hora vira `DATETIME2`.
        """
        types: dict[str, TypeEngine] = {}
        for column in dataframe.columns:
            series = dataframe[column]
            if pd.api.types.is_bool_dtype(series):
                types[column] = Boolean()
            elif pd.api.types.is_integer_dtype(series):
                types[column] = BigInteger()
            elif pd.api.types.is_float_dtype(series):
                types[column] = Float(precision=53)
            elif pd.api.types.is_datetime64_any_dtype(series):
                types[column] = _DATETIME_TYPE
            else:
                inferred = pd.api.types.infer_dtype(series, skipna=True)
                types[column] = _DATE_TYPE if inferred == "date" else _TEXT_TYPE
        return types
