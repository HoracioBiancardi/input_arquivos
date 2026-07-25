"""Conversão de DataFrames pandas para o formato Parquet."""

import io

import pandas as pd


class ParquetConverter:
    """Converte DataFrames pandas em bytes Parquet (engine pyarrow, compressão snappy)."""

    def to_bytes(self, dataframe: pd.DataFrame) -> bytes:
        """Serializa um DataFrame como Parquet.

        Args:
            dataframe: DataFrame a ser convertido.

        Returns:
            Conteúdo do arquivo Parquet, em bytes.
        """
        buffer = io.BytesIO()
        dataframe.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
        return buffer.getvalue()
