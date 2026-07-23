"""Schemas Pydantic para as rotas da API de upload e audit log."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.context import DestinationType, WriteMode
from app.models.upload_history import UploadStatus


class UploadHistoryResponse(BaseModel):
    """Representação de um registro de audit log retornada pela API.

    Attributes:
        id: Identificador interno do registro.
        filename: Nome original do arquivo enviado.
        context_name: Nome do contexto usado no upload.
        destination_type: Tipo de destino para o qual os dados foram enviados.
        destination_detail: Detalhe do destino final dos dados.
        write_mode: Modo de escrita usado, quando aplicável.
        status: Resultado do processamento (sucesso ou erro).
        row_count: Quantidade de linhas geradas, quando aplicável.
        error_message: Mensagem de erro, quando `status` é ERROR.
        uploaded_by: Nome do usuário que realizou o upload.
        created_at: Data/hora do upload.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    context_name: str
    destination_type: DestinationType
    destination_detail: str
    write_mode: WriteMode | None
    status: UploadStatus
    row_count: int | None
    error_message: str | None
    uploaded_by: str
    created_at: datetime
