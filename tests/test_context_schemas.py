"""Testes dos schemas Pydantic de context, com foco nas regras de validação de dados por coluna."""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from input_arquivos.backend.models.context import DestinationType, ImageMode, PdfMode, WriteMode
from input_arquivos.backend.schemas.context import ColumnRule, ContextCreateRequest, ContextResponse


def _base_create_kwargs() -> dict:
    """Kwargs mínimos válidos para `ContextCreateRequest`, com um destino que não exige mais campos."""
    return {
        "name": "vendas",
        "destination_type": DestinationType.LOCAL,
        "local_path": "data/local_storage",
    }


def test_create_request_accepts_valid_column_rules() -> None:
    """Uma lista de regras sem colunas duplicadas deve ser aceita normalmente."""
    request = ContextCreateRequest(
        **_base_create_kwargs(),
        column_rules=[
            {"column": "valor", "type": "decimal", "required": True},
            {"column": "produto", "type": "text"},
        ],
    )

    assert request.column_rules == [
        ColumnRule(column="valor", type="decimal", required=True),
        ColumnRule(column="produto", type="text", required=False),
    ]


def test_create_request_rejects_duplicate_rule_columns() -> None:
    """Duas regras para a mesma coluna (case-insensitive) devem ser rejeitadas."""
    with pytest.raises(ValidationError):
        ContextCreateRequest(
            **_base_create_kwargs(),
            column_rules=[
                {"column": "valor", "type": "decimal"},
                {"column": "Valor", "type": "text"},
            ],
        )


def test_column_rule_rejects_blank_column_name() -> None:
    """Uma regra sem nome de coluna (só espaços) deve ser rejeitada."""
    with pytest.raises(ValidationError):
        ColumnRule(column="   ", type="text")


def _context_response_kwargs(column_rules: object) -> dict:
    """Kwargs mínimos para `ContextResponse`, variando apenas `column_rules`."""
    return {
        "id": 1,
        "name": "vendas",
        "destination_type": DestinationType.LOCAL,
        "minio_bucket": None,
        "db_connection_string": None,
        "db_schema_name": "dbo",
        "db_table": None,
        "local_path": "data/local_storage",
        "allowed_file_types": "excel,csv,pdf",
        "expected_columns": None,
        "column_rules": column_rules,
        "default_write_mode": WriteMode.APPEND,
        "pdf_mode": PdfMode.METADATA_ONLY,
        "image_mode": ImageMode.RAW_ARCHIVE,
        "active": True,
        "created_at": datetime.now(timezone.utc),
    }


def test_context_response_parses_raw_json_string() -> None:
    """`ContextResponse` deve converter a string JSON crua (formato salvo no banco) para uma lista."""
    raw = json.dumps([{"column": "valor", "type": "decimal", "required": True}])

    response = ContextResponse(**_context_response_kwargs(raw))

    assert response.column_rules == [ColumnRule(column="valor", type="decimal", required=True)]


@pytest.mark.parametrize("raw", [None, ""])
def test_context_response_parses_empty_value_as_empty_list(raw: str | None) -> None:
    """`None`/string vazia (sem regras configuradas) deve virar lista vazia."""
    response = ContextResponse(**_context_response_kwargs(raw))

    assert response.column_rules == []


def test_context_response_exposes_expected_columns() -> None:
    """`expected_columns` deve passar direto (usado pela UI para sugerir colunas ao configurar regras)."""
    kwargs = _context_response_kwargs([])
    kwargs["expected_columns"] = "produto,valor"

    response = ContextResponse(**kwargs)

    assert response.expected_columns == "produto,valor"


def test_context_response_tolerates_unknown_future_fields() -> None:
    """Um JSON com uma chave desconhecida (ex.: um campo `pattern` de uma versão futura) não deve quebrar o parse."""
    raw = json.dumps([{"column": "cpf", "type": "text", "required": True, "pattern": "^[0-9]{11}$"}])

    response = ContextResponse(**_context_response_kwargs(raw))

    assert response.column_rules == [ColumnRule(column="cpf", type="text", required=True)]
