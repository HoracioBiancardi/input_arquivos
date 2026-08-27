"""Testes do PartitionedKeyBuilder: sanitização de filename contra path traversal."""

from input_arquivos.backend.destinations.key_builder import PartitionedKeyBuilder


def test_build_key_with_normal_filename() -> None:
    """Um filename normal deve virar uma chave particionada por data, preservando o nome."""
    key = PartitionedKeyBuilder().build("vendas", "relatorio.csv")

    assert key.startswith("vendas/")
    assert key.endswith(".csv")
    assert "relatorio" in key


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
