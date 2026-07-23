"""Tipos de arquivo suportados pelo pipeline de ingestão e seu mapeamento para extensões."""

import enum


class FileType(str, enum.Enum):
    """Tipo de arquivo lógico que um context pode aceitar (independente da extensão exata)."""

    EXCEL = "excel"
    CSV = "csv"
    PDF = "pdf"


_EXTENSIONS_BY_TYPE: dict[FileType, tuple[str, ...]] = {
    FileType.EXCEL: (".xlsx", ".xls"),
    FileType.CSV: (".csv",),
    FileType.PDF: (".pdf",),
}


class FileTypeRegistry:
    """Mapeia tipos de arquivo lógicos (Excel/CSV/PDF) para extensões, e serializa a lista para o banco."""

    def extensions_for(self, file_type: FileType) -> tuple[str, ...]:
        """Retorna as extensões de arquivo associadas a um tipo lógico.

        Args:
            file_type: Tipo de arquivo lógico.

        Returns:
            Tupla de extensões (com o ponto, em minúsculas) para esse tipo.
        """
        return _EXTENSIONS_BY_TYPE[file_type]

    def type_for_extension(self, extension: str) -> FileType | None:
        """Descobre o tipo lógico correspondente a uma extensão de arquivo.

        Args:
            extension: Extensão do arquivo em minúsculas (com o ponto, ex. ".csv").

        Returns:
            O `FileType` correspondente, ou `None` se a extensão não for reconhecida.
        """
        for file_type, extensions in _EXTENSIONS_BY_TYPE.items():
            if extension in extensions:
                return file_type
        return None

    def extensions_for_types(self, file_types: list[FileType]) -> list[str]:
        """Retorna todas as extensões associadas a uma lista de tipos lógicos.

        Args:
            file_types: Tipos de arquivo lógicos permitidos.

        Returns:
            Lista de extensões (com o ponto) para esses tipos.
        """
        return [extension for file_type in file_types for extension in self.extensions_for(file_type)]

    def serialize(self, file_types: list[FileType]) -> str:
        """Serializa uma lista de tipos de arquivo para salvar em `Context.allowed_file_types`.

        Args:
            file_types: Tipos de arquivo a serializar.

        Returns:
            Valores separados por vírgula (ex. "excel,csv").
        """
        return ",".join(file_type.value for file_type in file_types)

    def deserialize(self, value: str | None) -> list[FileType]:
        """Lê o valor salvo em `Context.allowed_file_types` de volta para uma lista de `FileType`.

        Args:
            value: Valor salvo no banco, ou `None`/vazio.

        Returns:
            Lista de `FileType` permitidos. Se `value` for vazio, retorna todos os
            tipos suportados (comportamento permissivo por padrão).
        """
        if not value:
            return list(FileType)
        return [FileType(item) for item in value.split(",") if item]
