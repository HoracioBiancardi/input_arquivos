"""Testes do FileTypeRegistry: mapeamento entre tipos lógicos de arquivo e extensões."""

from app.ingestion.file_types import FileType, FileTypeRegistry


def test_type_for_extension_resolves_known_extensions() -> None:
    """Extensões conhecidas devem resolver para o `FileType` correto."""
    registry = FileTypeRegistry()

    assert registry.type_for_extension(".xlsx") == FileType.EXCEL
    assert registry.type_for_extension(".xls") == FileType.EXCEL
    assert registry.type_for_extension(".csv") == FileType.CSV
    assert registry.type_for_extension(".pdf") == FileType.PDF


def test_type_for_extension_returns_none_for_unknown_extension() -> None:
    """Uma extensão desconhecida deve retornar `None`, não levantar erro."""
    registry = FileTypeRegistry()

    assert registry.type_for_extension(".txt") is None


def test_deserialize_defaults_to_all_types_when_empty() -> None:
    """Sem valor salvo (contexto antigo/sem configuração), todos os tipos são permitidos."""
    registry = FileTypeRegistry()

    assert set(registry.deserialize(None)) == set(FileType)
    assert set(registry.deserialize("")) == set(FileType)


def test_serialize_and_deserialize_round_trip() -> None:
    """Serializar e depois deserializar deve retornar a mesma lista de tipos."""
    registry = FileTypeRegistry()

    serialized = registry.serialize([FileType.EXCEL, FileType.CSV])

    assert serialized == "excel,csv"
    assert registry.deserialize(serialized) == [FileType.EXCEL, FileType.CSV]


def test_extensions_for_types_combines_extensions() -> None:
    """A lista de extensões para múltiplos tipos deve combinar todas elas."""
    registry = FileTypeRegistry()

    extensions = registry.extensions_for_types([FileType.EXCEL, FileType.CSV])

    assert set(extensions) == {".xlsx", ".xls", ".csv"}
