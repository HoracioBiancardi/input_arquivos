"""Construção da chave/caminho particionado por data usada pelos writers de arquivo (MinIO e local)."""

import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import PurePosixPath

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_NON_IDENTIFIER_CHARS = re.compile(r"[^a-z0-9_]+")


def _slugify(value: str) -> str:
    """Reduz um texto (nome de contexto) a um slug que também é um identificador SQL válido.

    Remove acentos (`"Relatório Vendas"` -> `"relatorio_vendas"`), passa para
    minúsculas e troca qualquer caractere fora de `[a-z0-9_]` por `_`, para
    que a pasta do contexto no MinIO possa virar direto o nome da tabela no
    SQL Server, sem colchetes. Um slug que começaria com dígito ganha o
    prefixo `t_`. O resultado nunca contém `/` nem `.`, então não consegue
    escapar da pasta de destino quando `LocalFileWriter` resolve o caminho.

    Args:
        value: Texto original (tipicamente `Context.name`).

    Returns:
        Slug seguro; `"arquivo"` se nada sobrar após a sanitização.
    """
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    slug = _NON_IDENTIFIER_CHARS.sub("_", ascii_value.lower()).strip("_") or "arquivo"
    return f"t_{slug}" if slug[0].isdigit() else slug


def _extension(filename: str) -> str:
    """Extrai a extensão (sem ponto) de um nome de arquivo possivelmente hostil.

    Args:
        filename: Nome de arquivo original (com extensão).

    Returns:
        Extensão sanitizada, ou `"bin"` se não houver.
    """
    name = PurePosixPath(filename.replace("\\", "/")).name
    extension = name.rsplit(".", 1)[1] if "." in name else ""
    return _UNSAFE_CHARS.sub("_", extension).strip("._").lower() or "bin"


class PartitionedKeyBuilder:
    """Monta chaves de objeto particionadas por data, nomeadas pelo contexto, com sufixo único."""

    def build(self, prefix: str, filename: str) -> str:
        """Monta uma chave no formato `{contexto}/{yyyy}/{mm}/{dd}/{contexto}_{yyyymmdd}_{HHMMSS}_{uuid curto}.ext`.

        O nome original do arquivo enviado não entra na chave (só a extensão
        dele) — ele continua registrado em `UploadHistory.filename`.

        Args:
            prefix: Nome do contexto; vira tanto a pasta raiz quanto o nome do arquivo.
            filename: Nome de arquivo do artefato, usado só para obter a extensão.

        Returns:
            Chave particionada por data, com um sufixo de UUID curto para
            evitar colisões entre uploads no mesmo segundo.
        """
        now = datetime.now(timezone.utc)
        slug = _slugify(prefix)
        short_uuid = uuid.uuid4().hex[:6]
        return f"{slug}/{now:%Y}/{now:%m}/{now:%d}/{slug}_{now:%Y%m%d}_{now:%H%M%S}_{short_uuid}.{_extension(filename)}"
