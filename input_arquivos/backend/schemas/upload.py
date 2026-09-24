"""Schemas Pydantic para as rotas da API de upload e audit log."""

from pydantic import BaseModel, ConfigDict

from input_arquivos.backend.models.context import DestinationType
from input_arquivos.backend.models.upload_history import LoadStatus, UploadStatus
from input_arquivos.backend.schemas.common import UtcDatetime


class UploadHistoryResponse(BaseModel):
    """Representação de um registro de audit log retornada pela API.

    Attributes:
        id: Identificador interno do registro.
        filename: Nome original do arquivo enviado.
        context_name: Nome do contexto usado no upload.
        destination_type: Tipo de destino para o qual os dados foram enviados.
        destination_detail: Detalhe do destino final dos dados.
        status: Resultado do processamento (sucesso ou erro).
        artifact_kind: Tipo do artefato gerado ("parquet", "raw_pdf" ou
            "raw_image"), usado pelo front-end para decidir se mostra o link
            de visualização da tabela. `None` se o upload falhou.
        row_count: Quantidade de linhas geradas, quando aplicável.
        error_message: Mensagem de erro, quando `status` é ERROR.
        load_status: Situação da carga no banco de destino (`None` = não se aplica).
        load_detail: Tabela de destino da última carga bem-sucedida.
        load_error: Erro da última carga, quando `load_status` é ERROR.
        loaded_at: Data/hora da última carga bem-sucedida.
        uploaded_by: Nome do usuário que realizou o upload.
        created_at: Data/hora do upload.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    context_name: str
    destination_type: DestinationType
    destination_detail: str
    status: UploadStatus
    artifact_kind: str | None
    row_count: int | None
    error_message: str | None
    load_status: LoadStatus | None = None
    load_detail: str | None = None
    load_error: str | None = None
    loaded_at: UtcDatetime | None = None
    uploaded_by: str
    created_at: UtcDatetime


class UploadPreviewResponse(BaseModel):
    """Recorte da tabela gerada por um upload, para a tela de visualização.

    Attributes:
        filename: Nome original do arquivo enviado.
        context_name: Nome do contexto usado no upload.
        columns: Nomes das colunas da tabela.
        rows: Linhas da tabela (até um limite), cada uma como lista de
            valores na mesma ordem de `columns`.
        total_row_count: Quantidade de linhas geradas por este upload.
        truncated: Se `rows` contém menos linhas do que `total_row_count`.
    """

    filename: str
    context_name: str
    columns: list[str]
    rows: list[list[object]]
    total_row_count: int | None
    truncated: bool
