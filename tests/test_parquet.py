"""Testes do conversor Parquet: garante que a serialização é um round-trip fiel."""

import io

import pandas as pd

from app.ingestion.parquet import ParquetConverter


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
