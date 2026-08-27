"""Construção da chave/caminho particionado por data usada pelos writers de arquivo (MinIO e local)."""

import re
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_stem(filename: str) -> str:
    """Reduz um nome de arquivo (possivelmente hostil) a um "stem" seguro para compor uma chave.

    Descarta qualquer componente de diretório (`PurePosixPath(...).name` já
    ignora `/` e, no Windows, `\\`) e troca qualquer caractere fora de
    `[A-Za-z0-9._-]` por `_`. Sem isso, um filename como `"../../evil"`
    (enviado pelo próprio usuário no upload) sobreviveria intacto na chave
    final e escaparia da pasta de destino quando `LocalFileWriter` resolvesse
    o caminho.

    Args:
        filename: Nome de arquivo original (com extensão).

    Returns:
        Um "stem" (sem extensão) seguro para compor uma chave de objeto/caminho.
    """
    name = PurePosixPath(filename.replace("\\", "/")).name
    stem = name.rsplit(".", 1)[0] if "." in name else name
    stem = _UNSAFE_CHARS.sub("_", stem).strip("._") or "arquivo"
    return stem


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
        stem = _sanitize_stem(filename)
        extension = filename.rsplit(".", 1)[1] if "." in filename else "bin"
        extension = _UNSAFE_CHARS.sub("_", extension) or "bin"
        short_uuid = uuid.uuid4().hex[:8]
        return f"{prefix}/{now:%Y}/{now:%m}/{now:%d}/{stem}_{now:%H%M%S}_{short_uuid}.{extension}"
