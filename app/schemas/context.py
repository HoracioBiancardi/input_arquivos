"""Schemas Pydantic para as rotas da API de contexts."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.models.context import DestinationType, PdfMode, WriteMode


def _validate_db_connection_string(destination_type: DestinationType, db_connection_string: str | None) -> None:
    """Garante que uma connection string plausível foi informada para destinos SQL Server.

    Args:
        destination_type: Tipo de destino selecionado.
        db_connection_string: Connection string informada, se houver.

    Raises:
        ValueError: Se `destination_type` for SQLSERVER e a connection string
            estiver vazia ou não parecer uma URL de conexão SQLAlchemy.
    """
    if destination_type != DestinationType.SQLSERVER:
        return
    if not db_connection_string or "://" not in db_connection_string:
        raise ValueError("Connection string do banco é obrigatória e deve ter o formato de uma URL (ex.: mssql+pyodbc://...).")


class ContextCreateRequest(BaseModel):
    """Corpo da requisição para criação de um novo context.

    Attributes:
        name: Nome único do context.
        destination_type: Tipo de destino (MinIO ou SQL Server).
        default_write_mode: Modo de escrita pré-selecionado na tela de upload.
        pdf_mode: Modo de tratamento de PDFs para este context.
        minio_bucket: Nome do bucket, quando `destination_type` é MINIO.
        db_connection_string: URL de conexão do banco, quando `destination_type` é SQLSERVER.
        db_schema_name: Schema da tabela de destino.
        db_table: Nome da tabela de destino.
        local_path: Pasta no disco local, quando `destination_type` é LOCAL.
        allowed_file_types: Tipos de arquivo aceitos, separados por vírgula
            (ex. "excel,csv"). Vazio equivale a aceitar todos os tipos.
        required_columns: Colunas que não podem ficar vazias num upload aceito
            para este contexto, separadas por vírgula. Vazio equivale a não
            exigir nenhuma coluna específica.
    """

    name: str
    destination_type: DestinationType
    default_write_mode: WriteMode = WriteMode.APPEND
    pdf_mode: PdfMode = PdfMode.METADATA_ONLY
    minio_bucket: str | None = None
    db_connection_string: str | None = None
    db_schema_name: str = "dbo"
    db_table: str | None = None
    local_path: str | None = None
    allowed_file_types: str = "excel,csv,pdf"
    required_columns: str = ""

    @model_validator(mode="after")
    def _validate_destination_fields(self) -> Self:
        """Garante que os campos exigidos pelo `destination_type` escolhido foram informados."""
        _validate_db_connection_string(self.destination_type, self.db_connection_string)
        return self


class ContextUpdateRequest(BaseModel):
    """Corpo da requisição para atualização de um context existente.

    Attributes:
        name: Nome único do context.
        destination_type: Tipo de destino (MinIO, SQL Server ou pasta local).
        default_write_mode: Modo de escrita pré-selecionado na tela de upload.
        pdf_mode: Modo de tratamento de PDFs para este context.
        minio_bucket: Nome do bucket, quando `destination_type` é MINIO.
        db_connection_string: URL de conexão do banco, quando `destination_type` é SQLSERVER.
        db_schema_name: Schema da tabela de destino.
        db_table: Nome da tabela de destino.
        local_path: Pasta no disco local, quando `destination_type` é LOCAL.
        allowed_file_types: Tipos de arquivo aceitos, separados por vírgula
            (ex. "excel,csv"). Vazio equivale a aceitar todos os tipos.
        required_columns: Colunas que não podem ficar vazias num upload aceito
            para este contexto, separadas por vírgula. Vazio equivale a não
            exigir nenhuma coluna específica.
        active: Se o context deve ficar ativo (visível na tela de upload).
    """

    name: str
    destination_type: DestinationType
    default_write_mode: WriteMode = WriteMode.APPEND
    pdf_mode: PdfMode = PdfMode.METADATA_ONLY
    minio_bucket: str | None = None
    db_connection_string: str | None = None
    db_schema_name: str = "dbo"
    db_table: str | None = None
    local_path: str | None = None
    allowed_file_types: str = "excel,csv,pdf"
    required_columns: str = ""
    active: bool = True

    @model_validator(mode="after")
    def _validate_destination_fields(self) -> Self:
        """Garante que os campos exigidos pelo `destination_type` escolhido foram informados."""
        _validate_db_connection_string(self.destination_type, self.db_connection_string)
        return self


class MinioConnectionTestRequest(BaseModel):
    """Corpo da requisição de teste de conectividade com um bucket MinIO.

    Attributes:
        bucket: Nome do bucket a verificar/criar.
    """

    bucket: str


class DbConnectionTestRequest(BaseModel):
    """Corpo da requisição de teste de conectividade com um banco de dados.

    Attributes:
        connection_string: URL de conexão SQLAlchemy do banco de destino.
    """

    connection_string: str


class LocalConnectionTestRequest(BaseModel):
    """Corpo da requisição de teste/criação de uma pasta local de destino.

    Attributes:
        path: Caminho da pasta local a verificar/criar.
    """

    path: str


class ConnectionTestResponse(BaseModel):
    """Resultado de um teste de conectividade com um destino.

    Attributes:
        success: Se a conexão foi bem-sucedida.
        message: Mensagem amigável descrevendo o resultado do teste.
    """

    success: bool
    message: str


class ContextResponse(BaseModel):
    """Representação de um context retornada pela API.

    Attributes:
        id: Identificador interno do context.
        name: Nome único do context.
        destination_type: Tipo de destino configurado.
        minio_bucket: Bucket MinIO configurado, se aplicável.
        db_connection_string: Connection string configurada, se aplicável.
        db_schema_name: Schema da tabela de destino, se aplicável.
        db_table: Tabela de destino, se aplicável.
        local_path: Pasta local configurada, se aplicável.
        allowed_file_types: Tipos de arquivo aceitos, separados por vírgula.
        required_columns: Colunas obrigatórias configuradas, separadas por vírgula.
        default_write_mode: Modo de escrita pré-selecionado.
        pdf_mode: Modo de tratamento de PDFs configurado.
        active: Se o context está ativo.
        created_at: Data de criação do context.
        destination_summary: Descrição curta e pronta para exibição do destino
            configurado (ex.: "MinIO → bucket-vendas"), computada no servidor
            para não duplicar essa lógica no front-end.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    destination_type: DestinationType
    minio_bucket: str | None
    db_connection_string: str | None
    db_schema_name: str
    db_table: str | None
    local_path: str | None
    allowed_file_types: str
    required_columns: str | None = None
    default_write_mode: WriteMode
    pdf_mode: PdfMode
    active: bool
    created_at: datetime
    destination_summary: str = ""


class AccessibleContextResponse(BaseModel):
    """Context acessível ao usuário atual na tela de upload, com metadados úteis à UI.

    Attributes:
        id: Identificador interno do context.
        name: Nome do context.
        destination_type: Tipo de destino configurado.
        minio_bucket: Bucket MinIO configurado, se aplicável.
        db_schema_name: Schema da tabela de destino, se aplicável.
        db_table: Tabela de destino, se aplicável.
        local_path: Pasta local configurada, se aplicável.
        default_write_mode: Modo de escrita pré-selecionado.
        allowed_extensions: Extensões de arquivo aceitas (com o ponto, ex. ".csv"),
            computadas no servidor a partir de `allowed_file_types`.
    """

    id: int
    name: str
    destination_type: DestinationType
    minio_bucket: str | None
    db_schema_name: str
    db_table: str | None
    local_path: str | None
    default_write_mode: WriteMode
    allowed_extensions: list[str]


class AccessibleContextsResponse(BaseModel):
    """Lista de contexts acessíveis ao usuário atual, com contexto adicional para a UI.

    Attributes:
        contexts: Contexts ativos que o usuário atual pode usar na tela de upload.
        has_any_active_context: Se existe ao menos um context ativo no sistema,
            usado para diferenciar "nenhum context liberado para você" de
            "nenhum context ativo cadastrado ainda".
        last_context_name: Último context usado pelo usuário, para pré-selecionar
            na tela de upload (só preenchido se ainda estiver entre os acessíveis).
    """

    contexts: list[AccessibleContextResponse]
    has_any_active_context: bool
    last_context_name: str | None = None
