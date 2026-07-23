"""Modelo ORM de Context: mapeamento entre um contexto de negócio e seu destino de dados."""

import enum
from datetime import datetime, timezone

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DestinationType(str, enum.Enum):
    """Tipo de destino para onde os dados de um contexto são enviados."""

    MINIO = "minio"
    SQLSERVER = "sqlserver"
    LOCAL = "local"


class WriteMode(str, enum.Enum):
    """Modo de escrita em uma tabela de banco de dados relacional."""

    APPEND = "append"
    CREATE_NEW = "create_new"


class PdfMode(str, enum.Enum):
    """Modo de tratamento de arquivos PDF configurado por contexto."""

    EXTRACT_TABLES = "extract_tables"
    METADATA_ONLY = "metadata_only"
    RAW_ARCHIVE = "raw_archive"


class Context(Base):
    """Contexto de negócio (ex.: "vendas") e o destino para o qual seus uploads são roteados.

    Attributes:
        id: Identificador interno do contexto.
        name: Nome único do contexto, exibido no seletor da tela de upload.
        destination_type: Tipo de destino (MinIO, SQL Server ou pasta local).
        minio_bucket: Nome do bucket MinIO, quando `destination_type` é MINIO.
        db_connection_string: URL de conexão SQLAlchemy do banco de destino,
            quando `destination_type` é SQLSERVER.
        db_schema: Schema da tabela de destino no banco de dados.
        db_table: Nome da tabela de destino no banco de dados.
        local_path: Pasta no disco local onde os artefatos são salvos, quando
            `destination_type` é LOCAL. Útil para testar o sistema por completo
            sem depender de um MinIO/SQL Server externo.
        default_write_mode: Modo de escrita pré-selecionado na tela de upload.
        pdf_mode: Modo de tratamento de PDFs enviados sob este contexto.
        allowed_file_types: Tipos de arquivo que este contexto aceita (valores de
            `FileType` separados por vírgula, ex. "excel,csv"). Uploads de um tipo
            fora dessa lista são rejeitados. Vazio/`None` equivale a aceitar todos.
        expected_columns: Colunas do último arquivo aceito para este contexto
            (separadas por vírgula, sem contar `data_envio`/`contexto`/`enviado_por`).
            Usado para avisar o usuário quando um novo arquivo tem colunas
            diferentes das anteriores, antes de confirmar o envio.
        required_columns: Colunas que não podem ficar vazias num upload aceito
            para este contexto (separadas por vírgula). Vazio/`None` equivale a
            não exigir nenhuma coluna específica. Diferente de `expected_columns`:
            uma violação aqui rejeita o upload direto, sem opção de confirmar.
        active: Indica se o contexto aparece como opção na tela de upload.
        created_at: Data de criação do registro.
        updated_at: Data da última atualização do registro.
    """

    __tablename__ = "contexts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    destination_type: Mapped[DestinationType] = mapped_column(SqlEnum(DestinationType))
    minio_bucket: Mapped[str | None] = mapped_column(String(255), default=None)
    db_connection_string: Mapped[str | None] = mapped_column(String(1000), default=None)
    db_schema_name: Mapped[str] = mapped_column(String(100), default="dbo")
    db_table: Mapped[str | None] = mapped_column(String(255), default=None)
    local_path: Mapped[str | None] = mapped_column(String(500), default=None)
    default_write_mode: Mapped[WriteMode] = mapped_column(SqlEnum(WriteMode), default=WriteMode.APPEND)
    pdf_mode: Mapped[PdfMode] = mapped_column(SqlEnum(PdfMode), default=PdfMode.METADATA_ONLY)
    allowed_file_types: Mapped[str] = mapped_column(String(50), default="excel,csv,pdf")
    expected_columns: Mapped[str | None] = mapped_column(Text, default=None)
    required_columns: Mapped[str | None] = mapped_column(Text, default=None)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
