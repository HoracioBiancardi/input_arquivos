"""Testes do PartitionedKeyBuilder: sanitização de filename contra path traversal."""

import re

from input_arquivos.backend.destinations.key_builder import PartitionedKeyBuilder


def test_build_key_names_file_after_context() -> None:
    """O arquivo gerado deve levar o nome do contexto, não o nome original enviado."""
    key = PartitionedKeyBuilder().build("vendas", "Relatório Final (1).csv")

    assert re.fullmatch(r"vendas/\d{4}/\d{2}/\d{2}/vendas_\d{8}_\d{6}_[0-9a-f]{6}\.csv", key)


def test_build_key_slugifies_context_name() -> None:
    """Nomes de contexto com acento, espaço ou maiúsculas viram um slug seguro na pasta e no arquivo."""
    key = PartitionedKeyBuilder().build("Notas Fiscais São Paulo", "x.parquet")

    assert key.startswith("notas_fiscais_sao_paulo/")
    assert "/notas_fiscais_sao_paulo_" in key
    assert " " not in key


def test_build_key_context_name_cannot_escape_prefix() -> None:
    """Um nome de contexto com `../` não deve gerar componentes de diretório extras."""
    key = PartitionedKeyBuilder().build("../../etc", "a.csv")

    assert ".." not in key
    assert key.count("/") == 4


def test_build_key_strips_directory_traversal_from_filename() -> None:
    """Um filename malicioso com `../` não deve sobreviver na chave gerada.

    Antes da correção, `stem = filename.rsplit(".", 1)[0]` preservava
    qualquer `../` no meio do nome, e o writer local resolvia esse caminho
    escapando da pasta configurada do contexto (escrita arbitrária no disco).
    """
    key = PartitionedKeyBuilder().build("vendas", "../../../etc/evil.py")

    assert ".." not in key
    assert "/etc/" not in key
    assert key.startswith("vendas/")
    assert key.endswith(".py")


def test_build_key_strips_absolute_path_from_filename() -> None:
    """Um filename absoluto também não deve escapar do prefixo do contexto."""
    key = PartitionedKeyBuilder().build("vendas", "/etc/passwd")

    assert key.startswith("vendas/")
    assert "/etc/" not in key


def test_build_key_sanitizes_unsafe_characters() -> None:
    """Caracteres fora de [A-Za-z0-9._-] no nome/extensão são substituídos, não propagados cru."""
    key = PartitionedKeyBuilder().build("vendas", "rel;rm -rf.csv")

    assert ";" not in key
    assert " " not in key


def test_build_key_context_slug_is_sql_identifier() -> None:
    """Pasta e nome do arquivo devem ser identificadores SQL válidos (sem `-`/`.`, sem dígito inicial)."""
    key = PartitionedKeyBuilder().build("2024-vendas.norte", "a.csv")

    assert key.startswith("t_2024_vendas_norte/")
    assert "/t_2024_vendas_norte_" in key
