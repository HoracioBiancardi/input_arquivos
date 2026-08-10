"""Schemas Pydantic para as rotas da API de contexts."""

import json
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from input_arquivos.backend.models.context import ColumnRuleType, DestinationType, ImageMode, PdfMode, WriteMode


class ColumnRule(BaseModel):
    """Regra de validação de dados para uma coluna de um context.

    Attributes:
        column: Nome da coluna à qual esta regra se aplica.
        type: Tipo de dado esperado para a coluna.
        required: Se `True`, a coluna deve estar presente no arquivo e não
            pode ter células vazias/nulas. Se `False`, a coluna é opcional
            (só é validada quando presente).
    """

    column: str
    type: ColumnRuleType
    required: bool = False

    @field_validator("column")
    @classmethod
    def _strip_column(cls, value: str) -> str:
        """Remove espaços nas pontas e garante que o nome da coluna não ficou vazio."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("Nome de coluna não pode ser vazio.")
        return stripped


def _validate_unique_rule_columns(column_rules: list[ColumnRule]) -> None:
    """Garante que não há duas regras para a mesma coluna (comparação case-insensitive).

    Args:
        column_rules: Lista de regras a validar.

    Raises:
        ValueError: Se houver mais de uma regra para a mesma coluna.
    """
    seen: set[str] = set()
    for rule in column_rules:
        key = rule.column.lower()
        if key in seen:
            raise ValueError(f"Regra duplicada para a coluna '{rule.column}'.")
        seen.add(key)


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
        image_mode: Modo de tratamento de imagens para este context.
        minio_bucket: Nome do bucket, quando `destination_type` é MINIO.
        db_connection_string: URL de conexão do banco, quando `destination_type` é SQLSERVER.
        db_schema_name: Schema da tabela de destino.
        db_table: Nome da tabela de destino.
        local_path: Pasta no disco local, quando `destination_type` é LOCAL.
        allowed_file_types: Tipos de arquivo aceitos, separados por vírgula
            (ex. "excel,csv"). Vazio equivale a aceitar todos os tipos.
        column_rules: Regras de validação de tipo/obrigatoriedade por coluna.
            Vazio equivale a não validar o conteúdo de nenhuma coluna.
    """

    name: str
    destination_type: DestinationType
    default_write_mode: WriteMode = WriteMode.APPEND
    pdf_mode: PdfMode = PdfMode.METADATA_ONLY
    image_mode: ImageMode = ImageMode.RAW_ARCHIVE
    minio_bucket: str | None = None
    db_connection_string: str | None = None
    db_schema_name: str = "dbo"
    db_table: str | None = None
    local_path: str | None = None
    allowed_file_types: str = "excel,csv,pdf"
    column_rules: list[ColumnRule] = []

    @model_validator(mode="after")
    def _validate_destination_fields(self) -> Self:
        """Garante que os campos exigidos pelo `destination_type` escolhido foram informados."""
        _validate_db_connection_string(self.destination_type, self.db_connection_string)
        return self

    @model_validator(mode="after")
    def _validate_column_rules(self) -> Self:
        """Garante que não há regras duplicadas para a mesma coluna."""
        _validate_unique_rule_columns(self.column_rules)
        return self


class ContextUpdateRequest(BaseModel):
    """Corpo da requisição para atualização de um context existente.

    Attributes:
        name: Nome único do context.
        destination_type: Tipo de destino (MinIO, SQL Server ou pasta local).
        default_write_mode: Modo de escrita pré-selecionado na tela de upload.
        pdf_mode: Modo de tratamento de PDFs para este context.
        image_mode: Modo de tratamento de imagens para este context.
        minio_bucket: Nome do bucket, quando `destination_type` é MINIO.
        db_connection_string: URL de conexão do banco, quando `destination_type` é SQLSERVER.
        db_schema_name: Schema da tabela de destino.
        db_table: Nome da tabela de destino.
        local_path: Pasta no disco local, quando `destination_type` é LOCAL.
        allowed_file_types: Tipos de arquivo aceitos, separados por vírgula
            (ex. "excel,csv"). Vazio equivale a aceitar todos os tipos.
        column_rules: Regras de validação de tipo/obrigatoriedade por coluna.
            Vazio equivale a não validar o conteúdo de nenhuma coluna.
        active: Se o context deve ficar ativo (visível na tela de upload).
    """

    name: str
    destination_type: DestinationType
    default_write_mode: WriteMode = WriteMode.APPEND
    pdf_mode: PdfMode = PdfMode.METADATA_ONLY
    image_mode: ImageMode = ImageMode.RAW_ARCHIVE
    minio_bucket: str | None = None
    db_connection_string: str | None = None
    db_schema_name: str = "dbo"
    db_table: str | None = None
    local_path: str | None = None
    allowed_file_types: str = "excel,csv,pdf"
    column_rules: list[ColumnRule] = []
    active: bool = True

    @model_validator(mode="after")
    def _validate_destination_fields(self) -> Self:
        """Garante que os campos exigidos pelo `destination_type` escolhido foram informados."""
        _validate_db_connection_string(self.destination_type, self.db_connection_string)
        return self

    @model_validator(mode="after")
    def _validate_column_rules(self) -> Self:
        """Garante que não há regras duplicadas para a mesma coluna."""
        _validate_unique_rule_columns(self.column_rules)
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
        expected_columns: Colunas do último arquivo aceito para este context,
            separadas por vírgula (ou `None` se ainda não houve upload aceito).
            Usado pela UI para sugerir nomes de coluna ao configurar regras.
        column_rules: Regras de validação de tipo/obrigatoriedade por coluna,
            já convertidas de JSON (armazenado no banco) para uma lista.
        default_write_mode: Modo de escrita pré-selecionado.
        pdf_mode: Modo de tratamento de PDFs configurado.
        image_mode: Modo de tratamento de imagens configurado.
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
    expected_columns: str | None = None
    column_rules: list[ColumnRule] = []
    default_write_mode: WriteMode
    pdf_mode: PdfMode
    image_mode: ImageMode
    active: bool
    created_at: datetime
    destination_summary: str = ""

    @field_validator("image_mode", mode="before")
    @classmethod
    def _default_image_mode(cls, value: object) -> object:
        """Trata `image_mode` nulo (contexts criados antes deste campo existir) como `RAW_ARCHIVE`."""
        return value or ImageMode.RAW_ARCHIVE

    @field_validator("column_rules", mode="before")
    @classmethod
    def _parse_column_rules(cls, value: object) -> object:
        """Converte a string JSON armazenada em `Context.column_rules` para uma lista.

        Retorna lista vazia para valores ausentes/vazios ou JSON inválido
        (config inconsistente não deve impedir a leitura do context).
        """
        if value is None or value == "":
            return []
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return []
        return value


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
