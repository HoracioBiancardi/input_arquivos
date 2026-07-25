"""Testes do ColumnMismatchChecker e do ColumnDataValidator."""

import json

import numpy as np
import pandas as pd

from app.backend.models.context import Context, DestinationType, PdfMode, WriteMode
from app.backend.services.column_check import ColumnDataValidator, ColumnMismatchChecker


def _make_context(
    expected_columns: str | None = None,
    column_rules: str | list[dict] | None = None,
) -> Context:
    """Cria um `Context` em memória com valores de `expected_columns`/`column_rules` para os testes."""
    return Context(
        id=1,
        name="vendas",
        destination_type=DestinationType.LOCAL,
        local_path=None,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        expected_columns=expected_columns,
        column_rules=json.dumps(column_rules) if isinstance(column_rules, list) else column_rules,
        active=True,
    )


def _tracked_dataframe(columns: list[str]) -> pd.DataFrame:
    """Simula o DataFrame já com as colunas de rastreabilidade injetadas pelo pipeline."""
    data = {"data_envio": ["x"], "contexto": ["vendas"], "enviado_por": ["maria"]}
    for column in columns:
        data[column] = ["valor"]
    return pd.DataFrame(data)


def test_check_returns_none_on_first_upload() -> None:
    """Sem `expected_columns` registrado ainda, não há divergência a reportar."""
    context = _make_context(expected_columns=None)
    dataframe = _tracked_dataframe(["produto", "valor"])

    assert ColumnMismatchChecker().check(context, dataframe) is None


def test_check_returns_none_when_columns_match() -> None:
    """Colunas idênticas às anteriores não geram divergência."""
    context = _make_context(expected_columns="produto,valor")
    dataframe = _tracked_dataframe(["produto", "valor"])

    assert ColumnMismatchChecker().check(context, dataframe) is None


def test_check_detects_missing_and_extra_columns() -> None:
    """Colunas removidas e adicionadas devem ser reportadas corretamente."""
    context = _make_context(expected_columns="produto,valor")
    dataframe = _tracked_dataframe(["produto", "quantidade"])

    mismatch = ColumnMismatchChecker().check(context, dataframe)

    assert mismatch is not None
    assert mismatch.missing_columns == ["valor"]
    assert mismatch.extra_columns == ["quantidade"]


def test_serialize_excludes_tracking_columns() -> None:
    """A serialização usada para salvar `expected_columns` não deve incluir as colunas injetadas."""
    dataframe = _tracked_dataframe(["produto", "valor"])

    serialized = ColumnMismatchChecker().serialize(dataframe)

    assert serialized == "produto,valor"


def test_column_data_validator_returns_none_without_rules() -> None:
    """Sem `column_rules` configurado, nenhuma violação deve ser reportada."""
    context = _make_context(column_rules=None)
    dataframe = _tracked_dataframe(["produto", "valor"])

    assert ColumnDataValidator().check(context, dataframe) is None


def test_column_data_validator_returns_none_when_all_valid() -> None:
    """Dados que respeitam todas as regras não geram violação."""
    context = _make_context(
        column_rules=[
            {"column": "valor", "type": "decimal", "required": True},
            {"column": "produto", "type": "text", "required": False},
        ]
    )
    dataframe = pd.DataFrame(
        {
            "data_envio": ["x", "x"],
            "contexto": ["vendas", "vendas"],
            "enviado_por": ["maria", "maria"],
            "produto": ["caneta", "lapis"],
            "valor": [10.5, 20],
        }
    )

    assert ColumnDataValidator().check(context, dataframe) is None


def test_column_data_validator_detects_type_mismatch() -> None:
    """Uma célula que não converte para o tipo declarado deve ser reportada."""
    context = _make_context(column_rules=[{"column": "valor", "type": "decimal", "required": False}])
    dataframe = pd.DataFrame(
        {
            "data_envio": ["x", "x"],
            "contexto": ["vendas", "vendas"],
            "enviado_por": ["maria", "maria"],
            "valor": ["abc", 10],
        }
    )

    violation = ColumnDataValidator().check(context, dataframe)

    assert violation is not None
    assert len(violation.details) == 1
    detail = violation.details[0]
    assert detail.column == "valor"
    assert detail.reason == "tipo_invalido"
    assert detail.bad_row_count == 1
    assert detail.sample[0].row_number == 2  # primeira linha de dados = índice 0 + 2
    assert detail.sample[0].value == "abc"


def test_column_data_validator_detects_required_violation_on_present_column() -> None:
    """Uma célula vazia numa regra obrigatória deve ser reportada, mesmo com a coluna presente."""
    context = _make_context(column_rules=[{"column": "produto", "type": "text", "required": True}])
    dataframe = pd.DataFrame(
        {
            "data_envio": ["x", "x"],
            "contexto": ["vendas", "vendas"],
            "enviado_por": ["maria", "maria"],
            "produto": ["caneta", ""],
        }
    )

    violation = ColumnDataValidator().check(context, dataframe)

    assert violation is not None
    assert len(violation.details) == 1
    assert violation.details[0].reason == "obrigatoria"
    assert violation.details[0].bad_row_count == 1


def test_column_data_validator_skips_missing_optional_column() -> None:
    """Uma regra opcional (`required=False`) para uma coluna ausente do arquivo simplesmente não se aplica."""
    context = _make_context(column_rules=[{"column": "inexistente", "type": "text", "required": False}])
    dataframe = _tracked_dataframe(["produto"])

    assert ColumnDataValidator().check(context, dataframe) is None


def test_column_data_validator_detects_missing_required_column() -> None:
    """Uma regra obrigatória (`required=True`) para uma coluna ausente do arquivo deve ser reportada."""
    context = _make_context(column_rules=[{"column": "inexistente", "type": "text", "required": True}])
    dataframe = _tracked_dataframe(["produto"])

    violation = ColumnDataValidator().check(context, dataframe)

    assert violation is not None
    assert len(violation.details) == 1
    detail = violation.details[0]
    assert detail.column == "inexistente"
    assert detail.reason == "coluna_ausente"
    assert detail.bad_row_count == len(dataframe)
    assert detail.sample == []


def test_column_data_validator_accepts_whole_float_as_integer() -> None:
    """Um float 'inteiro' vindo do Excel (10.0) deve passar numa regra `integer`; 10.5 não."""
    context = _make_context(column_rules=[{"column": "quantidade", "type": "integer", "required": False}])
    dataframe = pd.DataFrame(
        {
            "data_envio": ["x", "x"],
            "contexto": ["vendas", "vendas"],
            "enviado_por": ["maria", "maria"],
            "quantidade": [10.0, 10.5],
        }
    )

    violation = ColumnDataValidator().check(context, dataframe)

    assert violation is not None
    assert violation.details[0].bad_row_count == 1
    assert violation.details[0].sample[0].value == "10.5"


def test_column_data_validator_accepts_boolean_tokens() -> None:
    """Tokens textuais (sim/não) e booleanos nativos (incluindo numpy.bool_) devem ser aceitos."""
    context = _make_context(column_rules=[{"column": "ativo", "type": "boolean", "required": False}])
    dataframe = pd.DataFrame(
        {
            "data_envio": ["x", "x", "x"],
            "contexto": ["vendas", "vendas", "vendas"],
            "enviado_por": ["maria", "maria", "maria"],
            "ativo": ["sim", "não", np.bool_(True)],
        }
    )

    assert ColumnDataValidator().check(context, dataframe) is None


def test_column_data_validator_rejects_non_boolean_token() -> None:
    """Um valor que não é um token booleano reconhecido deve ser reportado."""
    context = _make_context(column_rules=[{"column": "ativo", "type": "boolean", "required": False}])
    dataframe = pd.DataFrame(
        {
            "data_envio": ["x"],
            "contexto": ["vendas"],
            "enviado_por": ["maria"],
            "ativo": ["talvez"],
        }
    )

    violation = ColumnDataValidator().check(context, dataframe)

    assert violation is not None
    assert violation.details[0].bad_row_count == 1


def test_column_data_validator_parses_dayfirst_dates() -> None:
    """Datas no formato brasileiro (DD/MM/AAAA) devem ser aceitas por uma regra `date`."""
    context = _make_context(column_rules=[{"column": "data_venda", "type": "date", "required": False}])
    dataframe = pd.DataFrame(
        {
            "data_envio": ["x", "x"],
            "contexto": ["vendas", "vendas"],
            "enviado_por": ["maria", "maria"],
            "data_venda": ["01/02/2026", "não é uma data"],
        }
    )

    violation = ColumnDataValidator().check(context, dataframe)

    assert violation is not None
    assert violation.details[0].bad_row_count == 1
    assert violation.details[0].sample[0].value == "não é uma data"


def test_column_data_validator_caps_sample_at_five_rows() -> None:
    """A amostra de linhas com problema deve ser limitada a 5, mesmo com mais violações."""
    context = _make_context(column_rules=[{"column": "valor", "type": "decimal", "required": False}])
    dataframe = pd.DataFrame(
        {
            "data_envio": ["x"] * 7,
            "contexto": ["vendas"] * 7,
            "enviado_por": ["maria"] * 7,
            "valor": ["abc"] * 7,
        }
    )

    violation = ColumnDataValidator().check(context, dataframe)

    assert violation is not None
    assert violation.details[0].bad_row_count == 7
    assert len(violation.details[0].sample) == 5


def test_column_data_validator_ignores_malformed_json() -> None:
    """JSON inválido em `column_rules` não deve quebrar a validação, apenas desabilitá-la."""
    context = _make_context(column_rules="{not valid json")
    dataframe = _tracked_dataframe(["produto"])

    assert ColumnDataValidator().check(context, dataframe) is None
