"""Testes do pipeline de ingestão: leitura de Excel/CSV/PDF/imagem/JSON/XML/TXT/YAML/ODS/HTML e
injeção das colunas de rastreabilidade.

Não há testes de PDF neste arquivo: gerar um PDF de teste exigiria uma
biblioteca de escrita de PDF (ex. reportlab), que não é uma dependência do
projeto. A lógica de leitura de PDF (`PdfTableReader`/`PdfMetadataReader`)
deve ser validada manualmente com um PDF real, conforme o plano de verificação.

Os testes de imagem (`ImageTableReader`) exigem a dependência opcional
`img2table[rapidocr]` instalada e são pulados automaticamente quando ela
não está disponível (ver `_OCR_AVAILABLE` abaixo).
"""

import io
import json

import pandas as pd
import pytest
import yaml
from PIL import Image, ImageDraw, ImageFont

from app.ingestion.pipeline import FileTypeNotAllowedError, IngestionPipeline, UnsupportedFileTypeError
from app.models.context import Context, DestinationType, ImageMode, PdfMode, WriteMode

try:
    import rapidocr  # noqa: F401

    _OCR_AVAILABLE = True
except ModuleNotFoundError:
    _OCR_AVAILABLE = False


def _make_context(
    name: str = "vendas",
    allowed_file_types: str | None = None,
    image_mode: ImageMode = ImageMode.RAW_ARCHIVE,
) -> Context:
    """Cria um `Context` em memória (sem persistir no banco) para uso nos testes."""
    return Context(
        id=1,
        name=name,
        destination_type=DestinationType.MINIO,
        minio_bucket="vendas",
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        image_mode=image_mode,
        allowed_file_types=allowed_file_types,
        active=True,
    )


def _make_table_png(rows: list[list[str]]) -> bytes:
    """Desenha uma tabela simples (grade + texto) em PNG, para testar o OCR local.

    Célula grande e texto com várias letras (nada de dígito/letra isolados):
    o detector de estrutura de tabela do img2table depende de contornos de
    caractere suficientes para estimar a escala da tabela, e falha em
    encontrar qualquer tabela com texto curto demais ou fonte pequena demais.
    """
    cell_width, cell_height = 320, 110
    width, height = cell_width * len(rows[0]), cell_height * len(rows)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=40)
    for row_index, row in enumerate(rows):
        for col_index, text in enumerate(row):
            x0, y0 = col_index * cell_width, row_index * cell_height
            draw.rectangle([x0, y0, x0 + cell_width, y0 + cell_height], outline="black", width=3)
            draw.text((x0 + 25, y0 + 35), text, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_process_injects_tracking_columns_for_csv() -> None:
    """As colunas data_envio, contexto e enviado_por devem ser as três primeiras do resultado."""
    csv_bytes = pd.DataFrame({"produto": ["A", "B"], "valor": [1, 2]}).to_csv(index=False).encode("utf-8")

    result = IngestionPipeline().process(csv_bytes, "vendas.csv", _make_context(), uploaded_by="maria")

    assert result.artifact_kind == "parquet"
    assert list(result.dataframe.columns[:3]) == ["data_envio", "contexto", "enviado_por"]
    assert (result.dataframe["contexto"] == "vendas").all()
    assert (result.dataframe["enviado_por"] == "maria").all()
    assert result.row_count == 2


def test_process_strips_utf8_bom_from_csv_columns() -> None:
    """Um CSV com BOM não deve fazer a primeira coluna virar "\\ufeffid" em vez de "id".

    Isso é importante para a checagem de divergência de colunas: sem o tratamento
    do BOM, um arquivo idêntico salvo com/sem BOM pareceria ter colunas diferentes.
    """
    csv_bytes = b"\xef\xbb\xbf" + b"id,valor\n1,10\n2,20\n"

    result = IngestionPipeline().process(csv_bytes, "vendas.csv", _make_context(), uploaded_by="maria")

    assert "id" in result.dataframe.columns
    assert not any(column.startswith("﻿") for column in result.dataframe.columns)


def test_process_reads_excel_file() -> None:
    """Um arquivo Excel deve ser lido e convertido corretamente."""
    buffer = io.BytesIO()
    pd.DataFrame({"produto": ["A", "B"], "valor": [1, 2]}).to_excel(buffer, index=False, engine="openpyxl")

    result = IngestionPipeline().process(buffer.getvalue(), "vendas.xlsx", _make_context(), uploaded_by="joao")

    assert result.row_count == 2
    assert "produto" in result.dataframe.columns


def test_process_raises_for_unsupported_extension() -> None:
    """Extensões não suportadas devem levantar `UnsupportedFileTypeError`."""
    with pytest.raises(UnsupportedFileTypeError):
        IngestionPipeline().process(b"conteudo", "arquivo.docx", _make_context(), uploaded_by="joao")


def test_process_raises_when_file_type_not_allowed_for_context() -> None:
    """Um Excel enviado para um contexto que só aceita CSV deve levantar `FileTypeNotAllowedError`."""
    csv_only_context = _make_context(allowed_file_types="csv")
    buffer = io.BytesIO()
    pd.DataFrame({"produto": ["A"]}).to_excel(buffer, index=False, engine="openpyxl")

    with pytest.raises(FileTypeNotAllowedError):
        IngestionPipeline().process(buffer.getvalue(), "vendas.xlsx", csv_only_context, uploaded_by="joao")


def test_process_allows_file_type_when_context_has_no_restriction() -> None:
    """Sem `allowed_file_types` configurado, o contexto aceita qualquer tipo suportado."""
    unrestricted_context = _make_context(allowed_file_types=None)
    csv_bytes = pd.DataFrame({"produto": ["A"]}).to_csv(index=False).encode("utf-8")

    result = IngestionPipeline().process(csv_bytes, "vendas.csv", unrestricted_context, uploaded_by="joao")

    assert result.row_count == 1


def test_process_archives_raw_image_without_ocr() -> None:
    """Em `image_mode=raw_archive`, a imagem original deve ser arquivada sem tentar OCR."""
    image_bytes = _make_table_png([["produto", "valor"], ["A", "1"]])
    context = _make_context(image_mode=ImageMode.RAW_ARCHIVE)

    result = IngestionPipeline().process(image_bytes, "vendas.png", context, uploaded_by="joao")

    assert result.artifact_kind == "raw_image"
    assert result.dataframe is None
    assert result.artifact_bytes == image_bytes


def test_process_treats_missing_image_mode_as_raw_archive() -> None:
    """Contexts antigos sem `image_mode` definido (`None`) devem se comportar como `raw_archive`."""
    image_bytes = _make_table_png([["produto", "valor"], ["A", "1"]])
    context = _make_context(image_mode=None)

    result = IngestionPipeline().process(image_bytes, "vendas.png", context, uploaded_by="joao")

    assert result.artifact_kind == "raw_image"
    assert result.dataframe is None


@pytest.mark.skipif(not _OCR_AVAILABLE, reason="img2table[rapidocr] não está instalado neste ambiente")
def test_process_reads_image_table_in_grid_mode() -> None:
    """Uma imagem com tabela em grade deve ser lida via OCR local e virar um DataFrame.

    Este é um smoke test de integração (pipeline → reader → img2table → RapidOCR):
    confirma que uma tabela É detectada e estruturada em linhas/colunas, mas não
    valida a fidelidade célula a célula do OCR sintético (fora do escopo automatizável
    sem imagens reais — ver seção de rollout do plano de implementação).
    """
    image_bytes = _make_table_png([["produto", "valor"], ["Produto A", "100"], ["Produto B", "200"]])
    context = _make_context(image_mode=ImageMode.TABLE_GRID)

    result = IngestionPipeline().process(image_bytes, "vendas.png", context, uploaded_by="joao")

    assert result.artifact_kind == "parquet"
    assert result.row_count == 2


@pytest.mark.skipif(not _OCR_AVAILABLE, reason="img2table[rapidocr] não está instalado neste ambiente")
def test_process_raises_when_no_table_found_in_image() -> None:
    """Uma imagem em branco, sem nenhuma tabela, deve levantar `ValueError`."""
    blank_image = Image.new("RGB", (200, 100), "white")
    buffer = io.BytesIO()
    blank_image.save(buffer, format="PNG")
    context = _make_context(image_mode=ImageMode.TABLE_GRID)

    with pytest.raises(ValueError, match="Nenhuma tabela"):
        IngestionPipeline().process(buffer.getvalue(), "vazia.png", context, uploaded_by="joao")


def test_process_reads_json_file() -> None:
    """Um JSON com uma lista de objetos na raiz deve ser lido e convertido corretamente."""
    json_bytes = json.dumps([{"produto": "A", "valor": 1}, {"produto": "B", "valor": 2}]).encode()

    result = IngestionPipeline().process(json_bytes, "vendas.json", _make_context(), uploaded_by="joao")

    assert result.row_count == 2
    assert "produto" in result.dataframe.columns


def test_process_raises_when_json_root_is_not_a_list_of_records() -> None:
    """Um JSON cuja raiz não é uma lista de objetos deve levantar `ValueError`."""
    json_bytes = json.dumps({"produto": "A", "valor": 1}).encode()

    with pytest.raises(ValueError, match="lista de objetos"):
        IngestionPipeline().process(json_bytes, "vendas.json", _make_context(), uploaded_by="joao")


def test_process_reads_yaml_file() -> None:
    """Um YAML com uma lista de objetos na raiz deve ser lido e convertido corretamente."""
    yaml_bytes = yaml.safe_dump([{"produto": "A", "valor": 1}, {"produto": "B", "valor": 2}]).encode()

    result = IngestionPipeline().process(yaml_bytes, "vendas.yaml", _make_context(), uploaded_by="joao")

    assert result.row_count == 2
    assert "produto" in result.dataframe.columns


def test_process_raises_when_yaml_root_is_not_a_list_of_records() -> None:
    """Um YAML cuja raiz não é uma lista de objetos deve levantar `ValueError`."""
    yaml_bytes = b"produto: A\nvalor: 1\n"

    with pytest.raises(ValueError, match="lista de objetos"):
        IngestionPipeline().process(yaml_bytes, "vendas.yaml", _make_context(), uploaded_by="joao")


def test_process_reads_xml_file() -> None:
    """Um XML com elementos repetidos na raiz deve ser lido e convertido corretamente."""
    xml_bytes = (
        b"<vendas><item><produto>A</produto><valor>1</valor></item>"
        b"<item><produto>B</produto><valor>2</valor></item></vendas>"
    )

    result = IngestionPipeline().process(xml_bytes, "vendas.xml", _make_context(), uploaded_by="joao")

    assert result.row_count == 2
    assert "produto" in result.dataframe.columns


def test_process_raises_when_xml_has_no_rows() -> None:
    """Um XML sem elementos filhos na raiz deve levantar `ValueError`."""
    with pytest.raises(ValueError, match="XML"):
        IngestionPipeline().process(b"<vendas></vendas>", "vendas.xml", _make_context(), uploaded_by="joao")


def test_process_reads_txt_file_as_delimited_text() -> None:
    """Um TXT com texto delimitado deve ser lido com a mesma lógica do CsvReader."""
    txt_bytes = b"produto;valor\nA;1\nB;2\n"

    result = IngestionPipeline().process(txt_bytes, "vendas.txt", _make_context(), uploaded_by="joao")

    assert result.row_count == 2
    assert "produto" in result.dataframe.columns


def test_process_reads_ods_file() -> None:
    """Uma planilha OpenDocument (.ods) deve ser lida e convertida corretamente."""
    buffer = io.BytesIO()
    pd.DataFrame({"produto": ["A", "B"], "valor": [1, 2]}).to_excel(buffer, index=False, engine="odf")

    result = IngestionPipeline().process(buffer.getvalue(), "vendas.ods", _make_context(), uploaded_by="joao")

    assert result.row_count == 2
    assert "produto" in result.dataframe.columns


def test_process_reads_html_file() -> None:
    """Uma tabela HTML deve ser extraída e convertida corretamente."""
    html_bytes = (
        b"<html><body><table>"
        b"<tr><th>produto</th><th>valor</th></tr>"
        b"<tr><td>A</td><td>1</td></tr><tr><td>B</td><td>2</td></tr>"
        b"</table></body></html>"
    )

    result = IngestionPipeline().process(html_bytes, "vendas.html", _make_context(), uploaded_by="joao")

    assert result.row_count == 2
    assert "produto" in result.dataframe.columns


def test_process_raises_when_no_table_found_in_html() -> None:
    """Um HTML sem nenhuma <table> deve levantar `ValueError`."""
    with pytest.raises(ValueError, match="Nenhuma tabela"):
        IngestionPipeline().process(b"<html><body><p>sem tabela</p></body></html>", "vazio.html", _make_context(), uploaded_by="joao")
