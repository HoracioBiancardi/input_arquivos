"""Comparação entre as colunas de um novo upload e as colunas esperadas de um contexto."""

import json
from dataclasses import dataclass

import pandas as pd

from app.models.context import Context

_TRACKING_COLUMNS = {"data_envio", "contexto", "enviado_por"}
_VALID_RULE_TYPES = {"text", "integer", "decimal", "date", "boolean"}
_BOOLEAN_TRUE_TOKENS = {"sim", "s", "true", "verdadeiro", "1", "yes", "y"}
_BOOLEAN_FALSE_TOKENS = {"não", "nao", "n", "false", "falso", "0", "no"}
_SAMPLE_LIMIT = 5


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


@dataclass(frozen=True)
class _ParsedColumnRule:
    """Representação interna de uma regra de `Context.column_rules`, já validada."""

    column: str
    rule_type: str
    required: bool


def _parse_column_rules(raw: str) -> list[_ParsedColumnRule]:
    """Faz o parse defensivo do JSON salvo em `context.column_rules`.

    Ignora silenciosamente entradas malformadas (JSON inválido, tipo
    desconhecido, campo `column` ausente) em vez de propagar exceção — um
    upload não deve quebrar por causa de uma configuração inconsistente de
    contexto.

    Args:
        raw: Conteúdo bruto de `context.column_rules`.

    Returns:
        Lista de regras válidas encontradas no JSON.
    """
    try:
        items = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(items, list):
        return []

    parsed: list[_ParsedColumnRule] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        column = item.get("column")
        rule_type = item.get("type")
        if not column or rule_type not in _VALID_RULE_TYPES:
            continue
        parsed.append(_ParsedColumnRule(column=column, rule_type=rule_type, required=bool(item.get("required"))))
    return parsed


@dataclass
class ColumnRuleSample:
    """Uma amostra de célula que violou uma regra de validação de dados.

    Attributes:
        row_number: Número da linha no arquivo original (1-based, contando o
            cabeçalho como linha 1 — a primeira linha de dados é a 2). Em
            uploads de PDF com `pdf_mode=extract_tables`, esse número não
            corresponde a nada visível no PDF original, já que as tabelas de
            várias páginas são concatenadas num único DataFrame.
        value: Valor original da célula, convertido para string (célula
            vazia/nula vira string vazia).
    """

    row_number: int
    value: str


@dataclass
class ColumnRuleViolation:
    """Descreve a violação de uma regra de validação de dados numa coluna.

    Attributes:
        column: Nome da coluna com problema.
        rule_type: Tipo de dado declarado na regra (`text`, `integer`,
            `decimal`, `date` ou `boolean`).
        reason: `"coluna_ausente"` (coluna obrigatória não veio no arquivo),
            `"obrigatoria"` (célula vazia numa regra obrigatória) ou
            `"tipo_invalido"` (célula não converte para o tipo declarado).
        bad_row_count: Quantidade total de linhas com esse problema nesta coluna.
        sample: Até `_SAMPLE_LIMIT` amostras das primeiras linhas com problema.
    """

    column: str
    rule_type: str
    reason: str
    bad_row_count: int
    sample: list[ColumnRuleSample]


@dataclass
class ColumnDataViolation:
    """Agrega todas as violações de regras de dados encontradas num upload.

    Attributes:
        details: Uma entrada por combinação (coluna, motivo) com problema.
    """

    details: list[ColumnRuleViolation]


class ColumnDataValidator:
    """Valida se os dados de cada coluna de um upload respeitam as regras de tipo/obrigatoriedade do contexto."""

    def check(self, context: Context, dataframe: pd.DataFrame) -> ColumnDataViolation | None:
        """Verifica cada regra de `context.column_rules` contra o DataFrame recebido.

        Uma regra marcada como `required=True` cuja coluna nem veio no
        arquivo também é uma violação (reason `"coluna_ausente"`) — isso
        cobre tanto a presença quanto o preenchimento da coluna com uma única
        configuração. Uma regra opcional (`required=False`) cuja coluna não
        veio no arquivo simplesmente não se aplica a este upload.

        Args:
            context: Contexto selecionado para o upload.
            dataframe: DataFrame já com as colunas de rastreabilidade injetadas.

        Returns:
            Um `ColumnDataViolation` se alguma coluna obrigatória estiver
            ausente ou alguma célula violar uma regra de tipo/obrigatoriedade,
            ou `None` se o contexto não tiver regras configuradas ou tudo passar.
        """
        if not context.column_rules:
            return None
        rules = _parse_column_rules(context.column_rules)
        if not rules:
            return None

        details: list[ColumnRuleViolation] = []
        for rule in rules:
            if rule.column not in dataframe.columns:
                if rule.required:
                    details.append(
                        ColumnRuleViolation(
                            column=rule.column,
                            rule_type=rule.rule_type,
                            reason="coluna_ausente",
                            bad_row_count=len(dataframe),
                            sample=[],
                        )
                    )
                continue
            details.extend(self._check_rule(dataframe[rule.column], rule))
        return ColumnDataViolation(details=details) if details else None

    def _check_rule(self, column: pd.Series, rule: _ParsedColumnRule) -> list[ColumnRuleViolation]:
        """Aplica uma única regra a uma coluna do DataFrame, retornando as violações encontradas."""
        violations: list[ColumnRuleViolation] = []
        empty_mask = self._empty_mask(column)

        if rule.required and empty_mask.any():
            violations.append(self._build_violation(column, rule, empty_mask, "obrigatoria"))

        non_empty = column[~empty_mask]
        if not non_empty.empty:
            valid_mask = self._coerces(non_empty, rule.rule_type)
            invalid = ~valid_mask
            if invalid.any():
                full_mask = pd.Series(False, index=column.index)
                full_mask.loc[non_empty.index[invalid.to_numpy()]] = True
                violations.append(self._build_violation(column, rule, full_mask, "tipo_invalido"))
        return violations

    def _empty_mask(self, column: pd.Series) -> pd.Series:
        """Máscara booleana elemento-a-elemento de células nulas ou em branco (mesma semântica de `_has_empty_cell`)."""
        is_na = column.isna()
        is_blank = column.astype(str).str.strip().eq("") & ~is_na
        return is_na | is_blank

    def _coerces(self, values: pd.Series, rule_type: str) -> pd.Series:
        """Retorna uma máscara booleana: `True` onde o valor é compatível com `rule_type`."""
        if rule_type == "text":
            return pd.Series(True, index=values.index)
        if rule_type in ("integer", "decimal"):
            numeric = pd.to_numeric(values, errors="coerce")
            ok = numeric.notna()
            if rule_type == "integer":
                ok = ok & numeric.apply(lambda v: bool(pd.notna(v)) and float(v).is_integer())
            return ok
        if rule_type == "date":
            parsed = pd.to_datetime(values, errors="coerce", dayfirst=True)
            return parsed.notna()
        if rule_type == "boolean":
            return values.apply(self._is_boolean_like)
        return pd.Series(False, index=values.index)  # inalcançável: rule_type já validado em _parse_column_rules

    def _is_boolean_like(self, value: object) -> bool:
        """Verifica se um valor é um booleano nativo ou um token textual reconhecido como sim/não."""
        if pd.api.types.is_bool(value):
            return True
        text = str(value).strip().lower()
        return text in _BOOLEAN_TRUE_TOKENS or text in _BOOLEAN_FALSE_TOKENS

    def _build_violation(
        self, column: pd.Series, rule: _ParsedColumnRule, mask: pd.Series, reason: str
    ) -> ColumnRuleViolation:
        """Monta um `ColumnRuleViolation` a partir de uma máscara de linhas com problema."""
        bad_positions = list(column.index[mask])
        sample = [
            ColumnRuleSample(row_number=int(pos) + 2, value="" if pd.isna(column.loc[pos]) else str(column.loc[pos]))
            for pos in bad_positions[:_SAMPLE_LIMIT]
        ]
        return ColumnRuleViolation(
            column=rule.column,
            rule_type=rule.rule_type,
            reason=reason,
            bad_row_count=len(bad_positions),
            sample=sample,
        )
