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
