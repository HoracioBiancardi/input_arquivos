"""Leitores de arquivo: convertem os bytes de um upload em um DataFrame pandas."""

import io
import json
import re
from typing import Protocol

import numpy as np
import pandas as pd
import pdfplumber
import yaml
from img2table.document import Image as Img2TableImage
from img2table.ocr import RapidOCR


MAX_ROWS = 200_000
"""Teto de linhas aceito por leitores tabulares (Excel/ODS) em uma única leitura.

Não existe validação de tamanho de arquivo (bytes) que proteja contra um
arquivo pequeno com um número absurdo de linhas — um .xlsx de ~28 MB pode
conter 300 mil linhas x 40 colunas e travar o processo por minutos de CPU
durante o parsing. Este teto falha rápido, antes do restante do pipeline
(validação de colunas, conversão para Parquet, escrita no destino) rodar
sobre um DataFrame gigante.
"""

MAX_PAGES = 200
"""Teto de páginas aceito por leitores de PDF (`PdfTableReader`/`StockLotsOcrReader`).

`StockLotsOcrReader` rasteriza cada página a `_STOCK_OCR_RESOLUTION` DPI e
roda OCR nela — um PDF com muitas páginas pode consumir CPU/memória de forma
desproporcional ao tamanho do arquivo em bytes.
"""


class UploadTooLargeError(ValueError):
    """Erro levantado quando um arquivo excede o teto de linhas/páginas que o pipeline processa.

    Deriva de `ValueError` para se encaixar no mesmo tratamento de erro já
    existente em `UploadService`/`routes_upload` (qualquer `Exception` durante
    a leitura vira um registro de auditoria com status de erro, sem travar
    a requisição nem expor um 500 genérico).
    """


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

        Raises:
            UploadTooLargeError: Se a planilha tiver mais de `MAX_ROWS` linhas.
        """
        dataframe = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
        if len(dataframe) > MAX_ROWS:
            raise UploadTooLargeError(
                f"Esta planilha tem {len(dataframe)} linhas, acima do limite de {MAX_ROWS} linhas por arquivo."
            )
        return dataframe


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
            UploadTooLargeError: Se o PDF tiver mais de `MAX_PAGES` páginas.
        """
        frames: list[pd.DataFrame] = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                raise UploadTooLargeError(
                    f"Este PDF tem {len(pdf.pages)} páginas, acima do limite de {MAX_PAGES} páginas por arquivo."
                )
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


_STOCK_MASTER_RE = re.compile(r"^(\d+)\s+(.*\S)\s+PA\d+$")
_STOCK_EAN_UN_RE = re.compile(r"^(\d+)\s+(\w+)$")
_STOCK_NLOTE_MARKERS = ("Nº lote", "N° lote")
_STOCK_FILIAL_X = (340, 430)
_STOCK_EAN_X = (1150, 1400)
_STOCK_AVARIA_X = (1400, 1495)
_STOCK_QT_UNIT_X = (1495, 1560)
_STOCK_EST_ATUAL_X = (1580, 1750)
_STOCK_LOTE_X = (40, 170)
_STOCK_VALIDADE_X = (200, 370)
_STOCK_QTD_X = (360, 570)
_STOCK_OCR_RESOLUTION = 216


class StockLotsOcrReader:
    """Extrai, via OCR, relatórios de "Relação de Estoque" com produto mestre + sub-linhas
    de lote/validade/quantidade disponível, expandindo para uma linha por lote.

    Feito para PDFs cujo texto foi vetorizado pelo gerador do relatório (0 caracteres e 0
    imagens extraíveis por `pdfplumber` — nem `PdfTableReader` nem `PdfMetadataReader`
    conseguem ler nada deles), o que exige rasterizar cada página e usar OCR (`RapidOCR`)
    mesmo se tratando de um PDF "nativo" em vez de um scan.

    As faixas de coluna (`_STOCK_*_X`) foram calibradas manualmente a partir de um único
    relatório de exemplo ("1130 - Relação de Estoque - versão: 36.02.01") renderizado a
    `_STOCK_OCR_RESOLUTION` DPI — um layout de relatório diferente (outra versão, outro
    conjunto de colunas) exige recalibrar essas constantes.
    """

    def read(self, file_bytes: bytes) -> pd.DataFrame:
        """Extrai todas as linhas produto+lote encontradas no PDF e as concatena em um DataFrame.

        Args:
            file_bytes: Conteúdo bruto do arquivo PDF.

        Returns:
            DataFrame com uma linha por lote, colunas `codigo`, `descricao`, `ean`, `un`,
            `avaria`, `qt_unit`, `filial`, `est_atual`, `lote`, `validade`, `qtd_disponivel`.

        Raises:
            ValueError: Se nenhuma linha de produto com lote puder ser extraída do PDF,
                ou se as dependências opcionais de OCR não estiverem instaladas.
            UploadTooLargeError: Se o PDF tiver mais de `MAX_PAGES` páginas.
        """
        try:
            from rapidocr import RapidOCR as RawRapidOcrEngine
        except ModuleNotFoundError as error:
            raise ValueError(
                "OCR indisponível: verifique se as dependências 'img2table[rapidocr]' estão instaladas."
            ) from error
        ocr = RawRapidOcrEngine(params={"Rec.lang_type": "pt", "Det.lang_type": "pt"})

        records: list[dict] = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                raise UploadTooLargeError(
                    f"Este PDF tem {len(pdf.pages)} páginas, acima do limite de {MAX_PAGES} páginas por arquivo."
                )
            for page in pdf.pages:
                image = page.to_image(resolution=_STOCK_OCR_RESOLUTION).original
                rows = self._ocr_rows(ocr, image)
                records.extend(self._parse_rows(rows))

        if not records:
            raise ValueError("Nenhum produto com lote foi encontrado neste PDF.")
        return pd.DataFrame(
            records,
            columns=[
                "codigo",
                "descricao",
                "ean",
                "un",
                "avaria",
                "qt_unit",
                "filial",
                "est_atual",
                "lote",
                "validade",
                "qtd_disponivel",
            ],
        )

    def _ocr_rows(self, ocr, image, row_tolerance: float = 12.0) -> list[list[tuple]]:
        """Roda o OCR na página rasterizada e agrupa as palavras detectadas em linhas visuais.

        Args:
            ocr: Instância carregada do motor `rapidocr.RapidOCR` (não o wrapper de
                `img2table.ocr.RapidOCR`, que não expõe chamada direta por palavra).
            image: Imagem da página renderizada (PIL).
            row_tolerance: Distância vertical (em pixels) máxima entre duas palavras
                para serem consideradas parte da mesma linha.

        Returns:
            Lista de linhas, cada uma uma lista de tuplas `(y0, x0, x1, texto)`
            ordenadas por posição horizontal.
        """
        result = ocr(np.asarray(image))
        words = []
        for box, text, _score in zip(result.boxes, result.txts, result.scores):
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
            words.append((min(ys), min(xs), max(xs), text))
        words.sort(key=lambda word: (word[0], word[1]))

        rows: list[list[tuple]] = []
        for word in words:
            for row in rows:
                if abs(row[0][0] - word[0]) <= row_tolerance:
                    row.append(word)
                    break
            else:
                rows.append([word])
        rows.sort(key=lambda row: row[0][0])
        for row in rows:
            row.sort(key=lambda word: word[1])
        return rows

    def _word_in_range(self, row: list[tuple], x_range: tuple[float, float]) -> str | None:
        """Retorna o texto da primeira palavra da linha cujo centro cai dentro de `x_range`."""
        low, high = x_range
        for _, x0, x1, text in row:
            if low <= (x0 + x1) / 2 <= high:
                return text
        return None

    def _parse_rows(self, rows: list[list[tuple]]) -> list[dict]:
        """Converte as linhas OCR em registros produto+lote, seguindo o layout mestre/detalhe.

        Cada linha "mestre" (produto) atualiza os dados correntes; cada linha de
        detalhe (lote/validade/qtd. disponível) gera um registro combinando os dados
        do produto atual com os do lote. Linhas de cabeçalho repetido ("Nº lote / Dt.
        validade / Qtd. disponível") são ignoradas.
        """
        records: list[dict] = []
        current: dict | None = None

        for row in rows:
            row_text = " ".join(text for *_rest, text in row)
            if any(marker in row_text for marker in _STOCK_NLOTE_MARKERS):
                continue

            master_match = None
            for _, _x0, _x1, text in row:
                match = _STOCK_MASTER_RE.match(text)
                if match:
                    master_match = match
                    break

            if master_match:
                codigo, descricao = master_match.groups()
                ean_un_raw = self._word_in_range(row, _STOCK_EAN_X)
                ean_un_match = _STOCK_EAN_UN_RE.match(ean_un_raw) if ean_un_raw else None
                avaria_raw = self._word_in_range(row, _STOCK_AVARIA_X)
                qt_unit_raw = self._word_in_range(row, _STOCK_QT_UNIT_X)
                est_atual_raw = self._word_in_range(row, _STOCK_EST_ATUAL_X)
                current = {
                    "codigo": codigo,
                    "descricao": descricao.rstrip(":").strip(),
                    "ean": ean_un_match.group(1) if ean_un_match else None,
                    "un": ean_un_match.group(2) if ean_un_match else None,
                    "avaria": int(avaria_raw) if avaria_raw and avaria_raw.isdigit() else None,
                    "qt_unit": int(qt_unit_raw) if qt_unit_raw and qt_unit_raw.isdigit() else None,
                    "filial": self._word_in_range(row, _STOCK_FILIAL_X),
                    "est_atual": float(est_atual_raw.replace(".", "").replace(",", ".")) if est_atual_raw else None,
                }
                continue

            lote = self._word_in_range(row, _STOCK_LOTE_X)
            validade = self._word_in_range(row, _STOCK_VALIDADE_X)
            qtd = self._word_in_range(row, _STOCK_QTD_X)
            if current is not None and lote and validade and qtd and lote.isdigit():
                records.append(
                    {**current, "lote": lote, "validade": validade, "qtd_disponivel": int(qtd.replace(".", ""))}
                )

        return records


class PdfMetadataReader:
    """Extrai apenas metadados e texto de um PDF, sem tentar estruturar tabelas."""

    def read(self, file_bytes: bytes, filename: str) -> pd.DataFrame:
        """Extrai o texto e a contagem de páginas de um PDF em uma única linha.

        Args:
            file_bytes: Conteúdo bruto do arquivo PDF.
            filename: Nome original do arquivo, incluído como coluna no resultado.

        Returns:
            DataFrame de uma linha com as colunas `filename`, `page_count` e `text_content`.

        Raises:
            UploadTooLargeError: Se o PDF tiver mais de `MAX_PAGES` páginas.
        """
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            if len(pdf.pages) > MAX_PAGES:
                raise UploadTooLargeError(
                    f"Este PDF tem {len(pdf.pages)} páginas, acima do limite de {MAX_PAGES} páginas por arquivo."
                )
            page_texts = [f"--- page {index} ---\n\n{page.extract_text() or ''}" for index, page in enumerate(pdf.pages, start=1)]
            page_count = len(pdf.pages)
        return pd.DataFrame(
            [{"filename": filename, "page_count": page_count, "text_content": "\n\n".join(page_texts)}]
        )


class ImageTableReader:
    """Extrai tabelas de uma imagem (foto/scan/screenshot) via OCR local e retorna como DataFrame."""

    def read(self, file_bytes: bytes, borderless: bool) -> pd.DataFrame:
        """Detecta e extrai tabelas de uma imagem, concatenando-as em um único DataFrame.

        Args:
            file_bytes: Conteúdo bruto do arquivo de imagem (.png/.jpg/.jpeg).
            borderless: Quando `True`, usa a heurística de tabelas sem grade visível
                (agrupamento por espaçamento/posição). Quando `False`, assume que a
                tabela tem linhas de grade detectáveis.

        Returns:
            DataFrame com as linhas de todas as tabelas encontradas na imagem, com a
            primeira linha de cada tabela promovida a cabeçalho de colunas.

        Raises:
            ValueError: Se nenhuma tabela puder ser extraída da imagem, ou se as
                dependências opcionais de OCR não estiverem instaladas.
        """
        # O construtor do `RapidOCR` carrega os modelos ONNX de detecção/reconhecimento
        # e levanta `ModuleNotFoundError` se o extra `img2table[rapidocr]` não estiver
        # instalado — por isso só é instanciado aqui, dentro de `read()`, e não no
        # pipeline, que cria todos os readers eagerly: instanciar isto de olhos fechados
        # no __init__ quebraria a ingestão de Excel/CSV/PDF também em ambientes sem essa
        # dependência opcional instalada.
        try:
            ocr = RapidOCR(params={"Rec.lang_type": "pt", "Det.lang_type": "pt"})
            document = Img2TableImage(src=file_bytes)
            extracted_tables = document.extract_tables(
                ocr=ocr,
                implicit_rows=borderless,
                borderless_tables=borderless,
                min_confidence=50,
            )
        except ModuleNotFoundError as error:
            raise ValueError(
                "OCR indisponível: verifique se as dependências 'img2table[rapidocr]' estão instaladas."
            ) from error

        frames: list[pd.DataFrame] = []
        for table in extracted_tables:
            raw = table.df
            if len(raw) < 2:
                continue
            header, *rows = raw.values.tolist()
            frames.append(pd.DataFrame(rows, columns=header))
        if not frames:
            raise ValueError("Nenhuma tabela foi encontrada nesta imagem.")
        return pd.concat(frames, ignore_index=True)


def _records_to_dataframe(data: object, formato: str) -> pd.DataFrame:
    """Converte uma lista de objetos (já decodificada de JSON/YAML) em DataFrame.

    Args:
        data: Estrutura de dados já decodificada (esperado: lista de objetos).
        formato: Nome do formato de origem, usado na mensagem de erro ("JSON"/"YAML").

    Returns:
        DataFrame com uma linha por objeto da lista, achatando um nível de aninhamento.

    Raises:
        ValueError: Se `data` não for uma lista de objetos.
    """
    if not isinstance(data, list) or not data or not all(isinstance(item, dict) for item in data):
        raise ValueError(f"O {formato} precisa ser uma lista de objetos (registros) na raiz.")
    return pd.json_normalize(data)


class JsonReader:
    """Lê arquivos JSON (lista de objetos na raiz) e retorna seu conteúdo como DataFrame."""

    def read(self, file_bytes: bytes) -> pd.DataFrame:
        """Decodifica um JSON e converte a lista de objetos da raiz em DataFrame.

        Args:
            file_bytes: Conteúdo bruto do arquivo .json.

        Returns:
            DataFrame com uma linha por objeto da lista.

        Raises:
            ValueError: Se o conteúdo não for um JSON válido, ou não for uma lista
                de objetos na raiz.
        """
        try:
            data = json.loads(file_bytes)
        except json.JSONDecodeError as error:
            raise ValueError(f"JSON inválido: {error}") from error
        return _records_to_dataframe(data, "JSON")


class YamlReader:
    """Lê arquivos YAML (lista de objetos na raiz) e retorna seu conteúdo como DataFrame."""

    def read(self, file_bytes: bytes) -> pd.DataFrame:
        """Decodifica um YAML e converte a lista de objetos da raiz em DataFrame.

        Args:
            file_bytes: Conteúdo bruto do arquivo .yaml/.yml.

        Returns:
            DataFrame com uma linha por objeto da lista.

        Raises:
            ValueError: Se o conteúdo não for um YAML válido, ou não for uma lista
                de objetos na raiz.
        """
        try:
            data = yaml.safe_load(file_bytes)
        except yaml.YAMLError as error:
            raise ValueError(f"YAML inválido: {error}") from error
        return _records_to_dataframe(data, "YAML")


class XmlReader:
    """Lê arquivos XML tabulares simples (elementos repetidos como linhas) e retorna como DataFrame."""

    def read(self, file_bytes: bytes) -> pd.DataFrame:
        """Extrai os elementos filhos da raiz do XML como linhas de um DataFrame.

        Args:
            file_bytes: Conteúdo bruto do arquivo .xml.

        Returns:
            DataFrame com uma linha por elemento filho da raiz do XML.

        Raises:
            ValueError: Se o XML não puder ser interpretado como uma tabela simples.
        """
        try:
            return pd.read_xml(io.BytesIO(file_bytes), parser="etree")
        except Exception as error:  # noqa: BLE001 - qualquer falha de parse deve virar erro amigável
            raise ValueError(f"Não foi possível interpretar este XML como uma tabela: {error}") from error


class OdsReader:
    """Lê planilhas OpenDocument (.ods, LibreOffice/OpenOffice Calc) e retorna como DataFrame."""

    def read(self, file_bytes: bytes) -> pd.DataFrame:
        """Lê a primeira planilha de um arquivo .ods.

        Args:
            file_bytes: Conteúdo bruto do arquivo .ods.

        Returns:
            DataFrame com os dados da primeira planilha do arquivo.

        Raises:
            ValueError: Se o pacote `odfpy` não estiver instalado no servidor.
            UploadTooLargeError: Se a planilha tiver mais de `MAX_ROWS` linhas.
        """
        try:
            dataframe = pd.read_excel(io.BytesIO(file_bytes), engine="odf")
        except ImportError as error:
            raise ValueError(
                "Leitura de .ods indisponível: verifique se o pacote 'odfpy' está instalado no servidor."
            ) from error
        if len(dataframe) > MAX_ROWS:
            raise UploadTooLargeError(
                f"Esta planilha tem {len(dataframe)} linhas, acima do limite de {MAX_ROWS} linhas por arquivo."
            )
        return dataframe


class HtmlReader:
    """Extrai tabelas (<table>) de uma página HTML e retorna como DataFrame."""

    def read(self, file_bytes: bytes) -> pd.DataFrame:
        """Extrai todas as tabelas encontradas em um HTML e as concatena em um único DataFrame.

        Cada tabela extraída ganha uma coluna `tabela` indicando de qual `<table>`
        da página ela veio, o que ajuda a rastrear a origem dos dados quando o
        HTML contém múltiplas tabelas.

        Args:
            file_bytes: Conteúdo bruto do arquivo .html/.htm.

        Returns:
            DataFrame com as linhas de todas as tabelas encontradas no HTML.

        Raises:
            ValueError: Se nenhuma tabela puder ser extraída do HTML, ou se as
                dependências de parsing (`beautifulsoup4`/`html5lib`) não
                estiverem instaladas no servidor.
        """
        try:
            tables = pd.read_html(io.BytesIO(file_bytes), flavor="bs4")
        except ImportError as error:
            raise ValueError(
                "Leitura de HTML indisponível: verifique se 'beautifulsoup4' e "
                "'html5lib' estão instalados no servidor."
            ) from error
        except ValueError as error:
            raise ValueError(f"Nenhuma tabela foi encontrada neste HTML: {error}") from error

        frames: list[pd.DataFrame] = []
        for table_index, frame in enumerate(tables, start=1):
            frame = frame.copy()
            frame["tabela"] = table_index
            frames.append(frame)
        return pd.concat(frames, ignore_index=True)
