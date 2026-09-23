"""Testes do conversor Parquet: garante que a serialização é um round-trip fiel."""

import io

import pandas as pd
import pytest

from input_arquivos.backend.ingestion.parquet import MixedColumnTypesError, ParquetConverter


def test_to_bytes_round_trips_dataframe_contents() -> None:
    """Converter para Parquet e ler de volta deve preservar linhas e colunas."""
    original = pd.DataFrame({"contexto": ["vendas", "vendas"], "valor": [10, 20]})

    parquet_bytes = ParquetConverter().to_bytes(original)
    restored = pd.read_parquet(io.BytesIO(parquet_bytes))

    pd.testing.assert_frame_equal(original, restored)


def test_to_bytes_returns_non_empty_bytes() -> None:
    """O resultado da conversão deve ser um conteúdo binário não vazio."""
    dataframe = pd.DataFrame({"coluna": [1, 2, 3]})

    parquet_bytes = ParquetConverter().to_bytes(dataframe)

    assert isinstance(parquet_bytes, bytes)
    assert len(parquet_bytes) > 0


def test_to_bytes_explains_mixed_type_column() -> None:
    """Uma coluna com número e texto misturados deve gerar um erro legível que cita a coluna."""
    dataframe = pd.DataFrame({"Data Fatura": [45000, "13/2026"]})

    with pytest.raises(MixedColumnTypesError, match="'Data Fatura' mistura tipos"):
        ParquetConverter().to_bytes(dataframe)
