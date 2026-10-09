"""Mês de competência dos envios em contextos mensais: formato, leitura do arquivo e mês corrente."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from input_arquivos.backend.models.context import Context, PeriodMode, PeriodSource
from input_arquivos.backend.models.upload_history import UploadHistory
from input_arquivos.backend.services.column_check import PERIOD_COLUMN, parse_dates

_PERIOD_PATTERN = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_MONTH_NAMES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
# Quantos meses diferentes citar na mensagem de arquivo com vários meses.
_MONTHS_IN_MESSAGE = 6

try:
    _LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
except ZoneInfoNotFoundError:  # sistema sem tzdata: o mês corrente cai no UTC
    _LOCAL_TZ = timezone.utc


class PeriodError(ValueError):
    """Erro levantado quando não dá para saber (ou aceitar) o mês de competência de um envio."""


def is_monthly(context: Context) -> bool:
    """Indica se o contexto controla os envios por mês de competência."""
    return context.period_mode == PeriodMode.MONTHLY


def is_valid_period(value: str | None) -> bool:
    """Indica se o texto é um mês no formato `AAAA-MM`."""
    return bool(value) and _PERIOD_PATTERN.match(value) is not None


def period_to_date(period: str) -> date:
    """Converte `AAAA-MM` no dia 1 do mês (valor gravado na coluna `competencia_envio`)."""
    year, month = period.split("-")
    return date(int(year), int(month), 1)


def period_label(period: str) -> str:
    """Nome do mês para mensagens: `2026-10` -> `outubro/2026`."""
    year, month = period.split("-")
    return f"{_MONTH_NAMES[int(month) - 1]}/{year}"


def current_period(now: datetime | None = None) -> str:
    """Mês corrente (`AAAA-MM`) no horário de Brasília, o mesmo que o usuário vê na tela."""
    moment = now or datetime.now(timezone.utc)
    return moment.astimezone(_LOCAL_TZ).strftime("%Y-%m")


def _as_utc(moment: datetime) -> datetime:
    """O SQLite devolve datas sem fuso; o valor foi gravado em UTC."""
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=timezone.utc)


def format_date_br(moment: datetime) -> str:
    """Data no horário de Brasília (`DD/MM/AAAA`), para mensagens ao usuário."""
    return _as_utc(moment).astimezone(_LOCAL_TZ).strftime("%d/%m/%Y")


def start_period(context: Context) -> str:
    """Primeiro mês esperado do contexto: `period_start`, ou o mês em que o contexto foi criado."""
    if is_valid_period(context.period_start):
        return context.period_start
    return current_period(_as_utc(context.created_at))


def resolve_period(context: Context, dataframe: pd.DataFrame | None, informed_period: str | None) -> str | None:
    """Descobre o mês de competência de um envio, conforme a configuração do contexto.

    Args:
        context: Contexto do envio.
        dataframe: Tabela lida do arquivo (`None` para PDF/imagem arquivados).
        informed_period: Mês escolhido pelo usuário na tela (`AAAA-MM`), usado
            só quando o contexto pede o mês no envio.

    Returns:
        O mês (`AAAA-MM`), ou `None` se o contexto não é mensal.

    Raises:
        PeriodError: Se o mês não foi informado/é inválido, se o arquivo não tem
            a coluna de data, se ela tem células vazias ou inválidas, ou se as
            linhas são de mais de um mês.
    """
    if not is_monthly(context):
        return None
    if context.period_source == PeriodSource.COLUMN:
        return _period_from_column(context, dataframe)
    if not is_valid_period(informed_period):
        raise PeriodError("Informe o mês de competência deste arquivo.")
    return informed_period


def _period_from_column(context: Context, dataframe: pd.DataFrame | None) -> str:
    """Lê o mês da coluna de data configurada no contexto; todas as linhas precisam ser do mesmo mês."""
    column = context.period_column or ""
    if dataframe is None:
        raise PeriodError(
            f"O contexto '{context.name}' tira o mês da coluna '{column}', então o arquivo precisa ter uma tabela."
        )
    if column not in dataframe.columns:
        raise PeriodError(f"O arquivo não tem a coluna '{column}', de onde sai o mês de competência.")
    if dataframe.empty:
        raise PeriodError("O arquivo não tem linhas, então não dá para saber o mês de competência.")

    values = dataframe[column]
    is_blank = values.isna() | values.astype(str).str.strip().eq("")
    if is_blank.any():
        raise PeriodError(f"A coluna '{column}' tem {int(is_blank.sum())} linha(s) sem data.")
    parsed = parse_dates(values)
    if parsed.isna().any():
        raise PeriodError(f"A coluna '{column}' tem {int(parsed.isna().sum())} linha(s) com data inválida.")

    months = sorted(parsed.dt.strftime("%Y-%m").unique())
    if len(months) > 1:
        listed = ", ".join(period_label(month) for month in months[:_MONTHS_IN_MESSAGE])
        more = f" e mais {len(months) - _MONTHS_IN_MESSAGE}" if len(months) > _MONTHS_IN_MESSAGE else ""
        raise PeriodError(
            f"O arquivo tem linhas de {len(months)} meses na coluna '{column}' ({listed}{more}). "
            "Envie um arquivo por mês."
        )
    return months[0]


def with_period_column(dataframe: pd.DataFrame, period: str) -> pd.DataFrame:
    """Devolve uma cópia da tabela com a coluna `competencia_envio` logo depois das de rastreabilidade.

    Raises:
        PeriodError: Se o arquivo já traz uma coluna com esse nome (reservado pelo sistema).
    """
    if PERIOD_COLUMN in dataframe.columns:
        raise PeriodError(f"O arquivo tem uma coluna '{PERIOD_COLUMN}', nome reservado pelo sistema. Renomeie-a.")
    tracked = dataframe.copy()
    position = min(3, len(tracked.columns))  # depois de data_envio, contexto e enviado_por
    tracked.insert(position, PERIOD_COLUMN, period_to_date(period))
    return tracked


@dataclass
class MonthStatus:
    """Situação de um mês na grade de competências de um contexto.

    Attributes:
        period: Mês (`AAAA-MM`).
        state: `sent` (tem envio vigente), `missing` (esperado e sem envio, até
            o mês corrente), `future` (depois do mês corrente, sem envio) ou
            `not_expected` (antes do primeiro mês esperado, sem envio).
        current: Envio(s) vigente(s) do mês — mais de um só com a política "permitir".
        version_count: Total de envios com sucesso do mês, contando os substituídos.
    """

    period: str
    state: str
    current: list[UploadHistory] = field(default_factory=list)
    version_count: int = 0


def build_year_grid(context: Context, uploads: list[UploadHistory], year: int, today: str) -> list[MonthStatus]:
    """Monta os 12 meses de um ano com o que já foi enviado e o que falta.

    Args:
        context: Contexto mensal.
        uploads: Envios com sucesso do contexto com competência no ano (ver
            `UploadService.list_period_uploads`).
        year: Ano da grade.
        today: Mês corrente (`AAAA-MM`), ver `current_period`.

    Returns:
        Uma entrada por mês, de janeiro a dezembro.
    """
    first_expected = start_period(context)
    months: list[MonthStatus] = []
    for month in range(1, 13):
        period = f"{year:04d}-{month:02d}"
        of_month = [upload for upload in uploads if upload.period == period]
        current = [upload for upload in of_month if upload.superseded_by is None]
        if current:
            state = "sent"
        elif period > today:
            state = "future"
        elif period < first_expected:
            state = "not_expected"
        else:
            state = "missing"
        months.append(MonthStatus(period=period, state=state, current=current, version_count=len(of_month)))
    return months
