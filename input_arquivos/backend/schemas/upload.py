"""Schemas Pydantic para as rotas da API de upload e audit log."""

from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict

from input_arquivos.backend.models.context import DestinationType, DuplicatePolicy, PeriodSource
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
        error_detail: Detalhe técnico de uma falha interna (só para admin).
        load_status: Situação da carga no banco de destino (`None` = não se aplica).
        load_detail: Tabela de destino da última carga bem-sucedida.
        load_error: Erro da última carga, quando `load_status` é ERROR.
        loaded_at: Data/hora da última carga bem-sucedida.
        period: Mês de competência (`AAAA-MM`), em contextos mensais.
        superseded_by: Id do envio do mesmo mês que substituiu este (`None` = vigente).
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
    error_detail: str | None = None
    load_status: LoadStatus | None = None
    load_detail: str | None = None
    load_error: str | None = None
    loaded_at: UtcDatetime | None = None
    period: str | None = None
    superseded_by: int | None = None
    uploaded_by: str
    created_at: UtcDatetime

    def redacted(self) -> "UploadHistoryResponse":
        """Versão para usuário comum, sem detalhes internos do servidor.

        Tira o caminho do servidor (ou o bucket) do destino, deixando só o nome
        do arquivo gravado, e troca o erro técnico da carga no banco (que pode
        trazer host, SQL e nomes de tabela) por uma mensagem genérica. O
        detalhe completo continua no log de auditoria do admin.

        Returns:
            Cópia do registro sem os campos internos.
        """
        return self.model_copy(
            update={
                "destination_detail": PurePosixPath(self.destination_detail.replace("\\", "/")).name,
                "error_detail": None,
                "load_error": (
                    "Falha ao carregar no banco. O administrador pode recarregar pelo log de auditoria."
                    if self.load_error
                    else None
                ),
            }
        )


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


class PeriodUploadSummary(BaseModel):
    """Envio vigente de um mês, como aparece na grade de competências (sem detalhes internos).

    Attributes:
        id: Identificador do envio.
        filename: Nome original do arquivo.
        uploaded_by: Quem enviou.
        created_at: Data/hora do envio.
        row_count: Quantidade de linhas.
        load_status: Situação da carga no banco (`None` = não se aplica).
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    uploaded_by: str
    created_at: UtcDatetime
    row_count: int | None
    load_status: LoadStatus | None = None


class PeriodMonthResponse(BaseModel):
    """Um mês da grade de competências.

    Attributes:
        period: Mês (`AAAA-MM`).
        state: `sent`, `missing`, `future` ou `not_expected` (ver `MonthStatus`).
        uploads: Envio(s) vigente(s) do mês.
        version_count: Total de envios do mês, contando os substituídos.
    """

    period: str
    state: str
    uploads: list[PeriodUploadSummary]
    version_count: int


class PeriodGridResponse(BaseModel):
    """Grade de 12 meses de um contexto mensal: o que já foi enviado e o que falta.

    Attributes:
        context_name: Nome do contexto.
        year: Ano da grade.
        current_period: Mês corrente (`AAAA-MM`, horário de Brasília).
        start_period: Primeiro mês esperado do contexto.
        period_source: De onde vem o mês (`column` ou `selector`).
        period_column: Coluna de data, quando o mês sai do arquivo.
        duplicate_policy: O que acontece ao reenviar um mês.
        months: Os 12 meses do ano, de janeiro a dezembro.
    """

    context_name: str
    year: int
    current_period: str
    start_period: str
    period_source: PeriodSource
    period_column: str | None
    duplicate_policy: DuplicatePolicy
    months: list[PeriodMonthResponse]
