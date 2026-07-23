"""Construção da chave/caminho particionado por data usada pelos writers de arquivo (MinIO e local)."""

import uuid
from datetime import datetime, timezone


class PartitionedKeyBuilder:
    """Monta chaves de objeto particionadas por data, com sufixo único para evitar colisões."""

    def build(self, prefix: str, filename: str) -> str:
        """Monta uma chave no formato `{prefix}/{yyyy}/{mm}/{dd}/{nome}_{HHMMSS}_{uuid curto}.ext`.

        Args:
            prefix: Prefixo da chave (tipicamente o nome do contexto).
            filename: Nome de arquivo original (com extensão) do artefato.

        Returns:
            Chave particionada por data, com um sufixo de UUID curto para
            evitar colisões entre uploads no mesmo segundo.
        """
        now = datetime.now(timezone.utc)
        stem = filename.rsplit(".", 1)[0]
        extension = filename.rsplit(".", 1)[1] if "." in filename else "bin"
        short_uuid = uuid.uuid4().hex[:8]
        return f"{prefix}/{now:%Y}/{now:%m}/{now:%d}/{stem}_{now:%H%M%S}_{short_uuid}.{extension}"
