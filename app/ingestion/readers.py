"""Leitores de arquivo: convertem os bytes de um upload em um DataFrame pandas."""

import io
from typing import Protocol

import pandas as pd
import pdfplumber


class FileReader(Protocol):
    """Contrato comum a todo leitor de arquivo usado pelo pipeline de ingestão."""

    def read(self, file_bytes: bytes) -> pd.DataFrame:
        """Lê os bytes de um arquivo e retorna um DataFrame pandas.

        Args:
            file_bytes: Conteúdo bruto do arquivo enviado.

        Returns:
            DataFrame com os dados extraídos do arquivo.
        """
        ...


class ExcelReader:
    """Lê arquivos Excel (.xlsx/.xls) e retorna seu conteúdo como DataFrame."""

    def read(self, file_bytes: bytes) -> pd.DataFrame:
        """Lê a primeira planilha de um arquivo Excel.

        Args:
            file_bytes: Conteúdo bruto do arquivo .xlsx/.xls.

        Returns:
            DataFrame com os dados da primeira planilha do arquivo.
        """
        return pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")


class CsvReader:
    """Lê arquivos CSV e retorna seu conteúdo como DataFrame."""

    def read(self, file_bytes: bytes) -> pd.DataFrame:
        """Lê um arquivo CSV, detectando automaticamente o delimitador.

        Args:
            file_bytes: Conteúdo bruto do arquivo .csv.

        Returns:
            DataFrame com os dados do arquivo CSV.
        """
        # "utf-8-sig" remove o BOM (marca de codificação) quando presente — comum em CSVs
        # exportados do Excel no Windows — e se comporta como "utf-8" normal quando ausente.
        # Sem isso, a primeira coluna do arquivo vira "﻿id" em vez de "id", o que
        # aparece como uma divergência de colunas falsa na comparação com uploads anteriores.
        return pd.read_csv(io.BytesIO(file_bytes), sep=None, engine="python", encoding="utf-8-sig")


class PdfTableReader:
    """Extrai tabelas de um PDF e retorna seus dados como DataFrame."""

    def read(self, file_bytes: bytes) -> pd.DataFrame:
        """Extrai todas as tabelas encontradas em um PDF e as concatena em um único DataFrame.

        Cada tabela extraída ganha uma coluna `pagina` indicando de qual
        página do PDF ela veio, o que ajuda a rastrear a origem dos dados
        quando o PDF contém múltiplas tabelas.

        Args:
            file_bytes: Conteúdo bruto do arquivo PDF.

        Returns:
            DataFrame com as linhas de todas as tabelas encontradas no PDF.

        Raises:
            ValueError: Se nenhuma tabela puder ser extraída do PDF.
        """
        frames: list[pd.DataFrame] = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                for table in page.extract_tables():
                    if not table or len(table) < 2:
                        continue
                    header, *rows = table
                    frame = pd.DataFrame(rows, columns=header)
                    frame["pagina"] = page_number
                    frames.append(frame)
        if not frames:
            raise ValueError("Nenhuma tabela foi encontrada neste PDF.")
        return pd.concat(frames, ignore_index=True)


class PdfMetadataReader:
    """Extrai apenas metadados e texto de um PDF, sem tentar estruturar tabelas."""

    def read(self, file_bytes: bytes, filename: str) -> pd.DataFrame:
        """Extrai o texto e a contagem de páginas de um PDF em uma única linha.

        Args:
            file_bytes: Conteúdo bruto do arquivo PDF.
            filename: Nome original do arquivo, incluído como coluna no resultado.

        Returns:
            DataFrame de uma linha com as colunas `filename`, `page_count` e `text_content`.
        """
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            page_texts = [f"--- page {index} ---\n\n{page.extract_text() or ''}" for index, page in enumerate(pdf.pages, start=1)]
            page_count = len(pdf.pages)
        return pd.DataFrame(
            [{"filename": filename, "page_count": page_count, "text_content": "\n\n".join(page_texts)}]
        )
