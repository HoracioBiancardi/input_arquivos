"""Modelo ORM de Context: mapeamento entre um contexto de negócio e seu destino de dados."""

import enum
from datetime import datetime, timezone

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from input_arquivos.backend.models.base import Base


class DestinationType(str, enum.Enum):
    """Tipo de destino para onde os dados de um contexto são enviados."""

    MINIO = "minio"
    LOCAL = "local"


class PdfMode(str, enum.Enum):
    """Modo de tratamento de arquivos PDF configurado por contexto."""

    EXTRACT_TABLES = "extract_tables"
    METADATA_ONLY = "metadata_only"
    RAW_ARCHIVE = "raw_archive"
    OCR_STOCK_LOTS = "ocr_stock_lots"


class ImageMode(str, enum.Enum):
    """Modo de tratamento de imagens (foto/scan/screenshot de tabela) configurado por contexto."""

    RAW_ARCHIVE = "raw_archive"
    TABLE_GRID = "table_grid"
    TABLE_BORDERLESS = "table_borderless"


class LoadMode(str, enum.Enum):
    """Como cada upload entra na tabela do contexto no banco de dados de destino."""

    APPEND = "append"
    REPLACE = "replace"


class PeriodMode(str, enum.Enum):
    """Se os envios de um contexto são controlados por mês de competência."""

    NONE = "none"
    MONTHLY = "monthly"


class PeriodSource(str, enum.Enum):
    """De onde vem o mês de competência de um envio, num contexto mensal."""

    COLUMN = "column"
    SELECTOR = "selector"


class DuplicatePolicy(str, enum.Enum):
    """O que fazer quando chega um envio de um mês que já tem envio vigente."""

    REPLACE = "replace"
    BLOCK = "block"
    ALLOW = "allow"


class ColumnRuleType(str, enum.Enum):
    """Tipo de dado esperado para uma coluna, usado em `Context.column_rules`."""

    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    BOOLEAN = "boolean"


class Context(Base):
    """Contexto de negócio (ex.: "vendas") e o destino para o qual seus uploads são roteados.

    Attributes:
        id: Identificador interno do contexto.
        name: Nome único do contexto, exibido no seletor da tela de upload.
        destination_type: Tipo de destino (MinIO ou pasta local).
        minio_bucket: Nome do bucket MinIO, quando `destination_type` é MINIO.
        local_path: Pasta no disco local onde os artefatos são salvos, quando
            `destination_type` é LOCAL. Útil para testar o sistema por completo
            sem depender de um MinIO externo.
        pdf_mode: Modo de tratamento de PDFs enviados sob este contexto.
        image_mode: Modo de tratamento de imagens enviadas sob este contexto.
        allowed_file_types: Tipos de arquivo que este contexto aceita (valores de
            `FileType` separados por vírgula, ex. "excel,csv"). Uploads de um tipo
            fora dessa lista são rejeitados. Vazio/`None` equivale a aceitar todos.
        expected_columns: Colunas do último arquivo aceito para este contexto
            (separadas por vírgula, sem contar `data_envio`/`contexto`/`enviado_por`).
            Usado para avisar o usuário quando um novo arquivo tem colunas
            diferentes das anteriores, antes de confirmar o envio.
        column_rules: Regras de validação de tipo/obrigatoriedade por coluna,
            serializadas como JSON (lista de objetos `{"column", "type",
            "required"}`). Diferente de `expected_columns`: uma violação aqui
            rejeita o upload direto, sem opção de confirmar. Uma regra com
            `required=True` cobre tanto a ausência da coluna no arquivo
            quanto células vazias nela quando presente.
        load_to_database: Se `True`, além de gravar o Parquet no MinIO/pasta
            local, cada upload bem-sucedido é carregado como linhas na tabela
            do contexto no banco de dados de destino (conexão global em
            `/admin/settings`). `None` (contexts anteriores ao campo) equivale a `False`.
        db_schema: Schema da tabela de destino. Vazio usa o schema padrão da
            conexão (ex.: `dbo` no SQL Server).
        db_table: Nome da tabela de destino. Vazio usa o slug do nome do
            contexto (o mesmo da pasta no MinIO).
        load_mode: `APPEND` acumula as linhas de todos os uploads (cada linha
            leva `id_envio`, e recarregar um upload não duplica); `REPLACE`
            apaga todo o conteúdo da tabela antes de inserir o upload.
            `None` equivale a `APPEND`. Num contexto mensal não se aplica: a
            carga substitui só as linhas do mês do envio.
        period_mode: `MONTHLY` controla os envios por mês de competência (grade
            de meses enviados/faltantes e substituição de mês repetido).
            `None` equivale a `NONE`.
        period_source: Num contexto mensal, se o mês sai de uma coluna de data
            do arquivo (`COLUMN`) ou é informado pelo usuário no envio (`SELECTOR`).
        period_column: Nome da coluna de data, quando `period_source` é `COLUMN`.
        period_start: Primeiro mês esperado (`AAAA-MM`). Meses anteriores não
            aparecem como "faltando" na grade. Vazio usa o mês de criação do contexto.
        duplicate_policy: O que fazer quando o mês já tem envio: substituir
            (com confirmação), bloquear ou permitir os dois. `None` equivale a `REPLACE`.
        sheet_name: Aba lida de planilhas com várias abas (Excel/ODS). `None`
            lê a primeira aba do arquivo.
        active: Indica se o contexto aparece como opção na tela de upload.
        created_at: Data de criação do registro.
        updated_at: Data da última atualização do registro.
    """

    __tablename__ = "contexts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    destination_type: Mapped[DestinationType] = mapped_column(SqlEnum(DestinationType))
    minio_bucket: Mapped[str | None] = mapped_column(String(255), default=None)
    local_path: Mapped[str | None] = mapped_column(String(500), default=None)
    pdf_mode: Mapped[PdfMode] = mapped_column(SqlEnum(PdfMode), default=PdfMode.METADATA_ONLY)
    image_mode: Mapped[ImageMode] = mapped_column(SqlEnum(ImageMode), default=ImageMode.RAW_ARCHIVE)
    allowed_file_types: Mapped[str] = mapped_column(String(50), default="excel,csv,pdf")
    expected_columns: Mapped[str | None] = mapped_column(Text, default=None)
    column_rules: Mapped[str | None] = mapped_column(Text, default=None)
    load_to_database: Mapped[bool | None] = mapped_column(default=False)
    db_schema: Mapped[str | None] = mapped_column(String(128), default=None)
    db_table: Mapped[str | None] = mapped_column(String(128), default=None)
    load_mode: Mapped[LoadMode | None] = mapped_column(SqlEnum(LoadMode), default=LoadMode.APPEND)
    period_mode: Mapped[PeriodMode | None] = mapped_column(SqlEnum(PeriodMode), default=PeriodMode.NONE)
    period_source: Mapped[PeriodSource | None] = mapped_column(SqlEnum(PeriodSource), default=None)
    period_column: Mapped[str | None] = mapped_column(String(255), default=None)
    period_start: Mapped[str | None] = mapped_column(String(7), default=None)
    duplicate_policy: Mapped[DuplicatePolicy | None] = mapped_column(
        SqlEnum(DuplicatePolicy), default=DuplicatePolicy.REPLACE
    )
    sheet_name: Mapped[str | None] = mapped_column(String(255), default=None)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
