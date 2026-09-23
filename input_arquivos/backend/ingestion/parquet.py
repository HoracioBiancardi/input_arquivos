"""Conversão de DataFrames pandas para o formato Parquet."""

import io
import re

import pandas as pd
import pyarrow as pa

_FAILED_COLUMN = re.compile(r"Conversion failed for column (?P<column>.+?) with type")


class MixedColumnTypesError(ValueError):
    """Erro levantado quando uma coluna mistura tipos que o Parquet não consegue representar juntos."""


class ParquetConverter:
    """Converte DataFrames pandas em bytes Parquet (engine pyarrow, compressão snappy)."""

    def to_bytes(self, dataframe: pd.DataFrame) -> bytes:
        """Serializa um DataFrame como Parquet.

        Args:
            dataframe: DataFrame a ser convertido.

        Returns:
            Conteúdo do arquivo Parquet, em bytes.

        Raises:
            MixedColumnTypesError: Se alguma coluna misturar tipos incompatíveis
                (ex.: células de data/número e de texto na mesma coluna de uma
                planilha) — o pyarrow exige um tipo único por coluna, e a
                mensagem original dele é técnica demais para o usuário final.
        """
        buffer = io.BytesIO()
        try:
            dataframe.to_parquet(buffer, engine="pyarrow", compression="snappy", index=False)
        except (pa.ArrowInvalid, pa.ArrowTypeError) as error:
            match = _FAILED_COLUMN.search(str(error))
            column = f"'{match.group('column')}'" if match else "Uma das colunas"
            raise MixedColumnTypesError(
                f"A coluna {column} mistura tipos de valor diferentes (ex.: texto com número ou data). "
                "Padronize as células dessa coluna no arquivo, ou cadastre uma regra de tipo para ela "
                "no contexto — assim o sistema aponta exatamente quais linhas estão fora do padrão."
            ) from error
        return buffer.getvalue()
