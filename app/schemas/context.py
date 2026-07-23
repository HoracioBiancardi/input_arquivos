"""Schemas Pydantic para as rotas da API de contexts."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.context import DestinationType, PdfMode, WriteMode


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


class ContextResponse(BaseModel):
    """Representação de um context retornada pela API.

    Attributes:
        id: Identificador interno do context.
        name: Nome único do context.
        destination_type: Tipo de destino configurado.
        minio_bucket: Bucket MinIO configurado, se aplicável.
        db_schema_name: Schema da tabela de destino, se aplicável.
        db_table: Tabela de destino, se aplicável.
        local_path: Pasta local configurada, se aplicável.
        allowed_file_types: Tipos de arquivo aceitos, separados por vírgula.
        default_write_mode: Modo de escrita pré-selecionado.
        pdf_mode: Modo de tratamento de PDFs configurado.
        active: Se o context está ativo.
        created_at: Data de criação do context.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    destination_type: DestinationType
    minio_bucket: str | None
    db_schema_name: str
    db_table: str | None
    local_path: str | None
    allowed_file_types: str
    default_write_mode: WriteMode
    pdf_mode: PdfMode
    active: bool
    created_at: datetime
