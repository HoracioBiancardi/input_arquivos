"""Comparação entre as colunas de um novo upload e as colunas esperadas de um contexto."""

from dataclasses import dataclass

import pandas as pd

from app.models.context import Context

_TRACKING_COLUMNS = {"data_envio", "contexto", "enviado_por"}


@dataclass
class ColumnMismatch:
    """Descreve uma diferença entre as colunas de um novo arquivo e as do último arquivo aceito.

    Attributes:
        expected_columns: Colunas do último arquivo aceito para este contexto.
        incoming_columns: Colunas do arquivo que está sendo enviado agora.
        missing_columns: Colunas que existiam antes e não vieram neste arquivo.
        extra_columns: Colunas novas que não existiam nos envios anteriores.
    """

    expected_columns: list[str]
    incoming_columns: list[str]
    missing_columns: list[str]
    extra_columns: list[str]


class ColumnMismatchChecker:
    """Verifica se as colunas de um novo upload divergem das colunas já aceitas para o contexto."""

    def check(self, context: Context, dataframe: pd.DataFrame) -> ColumnMismatch | None:
        """Compara as colunas do DataFrame recebido com `context.expected_columns`.

        As colunas de rastreabilidade injetadas pelo pipeline (`data_envio`,
        `contexto`, `enviado_por`) são ignoradas na comparação, pois sempre
        estão presentes e não refletem a estrutura do arquivo original.

        Args:
            context: Contexto selecionado para o upload.
            dataframe: DataFrame já com as colunas de rastreabilidade injetadas.

        Returns:
            Um `ColumnMismatch` descrevendo a diferença, ou `None` se não
            houver colunas esperadas registradas ainda (primeiro upload do
            contexto) ou se as colunas forem idênticas às anteriores.
        """
        if not context.expected_columns:
            return None

        expected = [name for name in context.expected_columns.split(",") if name]
        incoming = [name for name in dataframe.columns if name not in _TRACKING_COLUMNS]

        expected_set = set(expected)
        incoming_set = set(incoming)
        if expected_set == incoming_set:
            return None

        return ColumnMismatch(
            expected_columns=expected,
            incoming_columns=incoming,
            missing_columns=sorted(expected_set - incoming_set),
            extra_columns=sorted(incoming_set - expected_set),
        )

    def serialize(self, dataframe: pd.DataFrame) -> str:
        """Serializa as colunas "de negócio" de um DataFrame para salvar em `context.expected_columns`.

        Args:
            dataframe: DataFrame já com as colunas de rastreabilidade injetadas.

        Returns:
            Lista de colunas (excluindo as de rastreabilidade) separadas por vírgula.
        """
        return ",".join(name for name in dataframe.columns if name not in _TRACKING_COLUMNS)


@dataclass
class RequiredColumnViolation:
    """Descreve por que um upload não atende às colunas obrigatórias configuradas para o contexto.

    Attributes:
        missing_columns: Colunas obrigatórias que não vieram no arquivo.
        empty_columns: Colunas obrigatórias presentes no arquivo, mas com
            alguma célula vazia (nula ou string em branco).
    """

    missing_columns: list[str]
    empty_columns: list[str]


class RequiredColumnChecker:
    """Verifica se as colunas obrigatórias de um contexto vieram preenchidas num novo upload."""

    def check(self, context: Context, dataframe: pd.DataFrame) -> RequiredColumnViolation | None:
        """Compara as colunas obrigatórias do contexto contra o DataFrame recebido.

        Diferente de `ColumnMismatchChecker`, esta checagem não é sobre
        divergência em relação a um upload anterior: é uma regra de qualidade
        de dado fixa do contexto, então uma violação deve ser rejeitada
        diretamente, sem oferecer a opção de confirmar mesmo assim.

        Args:
            context: Contexto selecionado para o upload.
            dataframe: DataFrame já com as colunas de rastreabilidade injetadas.

        Returns:
            Um `RequiredColumnViolation` descrevendo o problema, ou `None` se
            o contexto não tiver colunas obrigatórias configuradas ou se todas
            estiverem presentes e preenchidas.
        """
        if not context.required_columns:
            return None

        required = [name for name in context.required_columns.split(",") if name]
        if not required:
            return None

        missing_columns = [name for name in required if name not in dataframe.columns]
        empty_columns = [
            name for name in required if name in dataframe.columns and self._has_empty_cell(dataframe[name])
        ]

        if not missing_columns and not empty_columns:
            return None
        return RequiredColumnViolation(missing_columns=missing_columns, empty_columns=empty_columns)

    def _has_empty_cell(self, column: pd.Series) -> bool:
        """Verifica se uma coluna tem alguma célula nula ou com string em branco.

        Args:
            column: Coluna do DataFrame a verificar.

        Returns:
            `True` se houver ao menos uma célula nula ou uma string vazia/só espaços.
        """
        if column.isna().any():
            return True
        non_null = column.dropna()
        if non_null.empty:
            return False
        return bool(non_null.astype(str).str.strip().eq("").any())
