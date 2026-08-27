"""Modelo ORM de SystemSettings: configuração global do MinIO, editável via admin e cifrada em repouso."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from input_arquivos.backend.models.base import Base
from input_arquivos.backend.models.encrypted_string import EncryptedString


class SystemSettings(Base):
    """Linha única (id fixo) com a configuração global do MinIO cadastrada via `/admin/settings`.

    Sobrepõe `Settings.minio_*` (vindas do `.env`) quando preenchida — ver
    `services/system_settings_service.py::SystemSettingsService.get_minio_config`
    para a lógica de precedência. Existir como tabela (em vez de só `.env`)
    permite reconfigurar o MinIO sem editar arquivo no servidor nem
    reiniciar o processo, e guardar a chave secreta cifrada em vez de texto
    puro.

    Attributes:
        id: Sempre `1` — esta tabela guarda uma única linha (singleton).
        minio_endpoint: Endereço (host:porta) do servidor MinIO.
        minio_access_key: Chave de acesso do MinIO.
        minio_secret_key: Chave secreta do MinIO, cifrada em repouso.
        minio_secure: Se a conexão com o MinIO deve usar HTTPS.
    """

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    minio_endpoint: Mapped[str | None] = mapped_column(String(255), default=None)
    minio_access_key: Mapped[str | None] = mapped_column(EncryptedString(255), default=None)
    minio_secret_key: Mapped[str | None] = mapped_column(EncryptedString(255), default=None)
    minio_secure: Mapped[bool | None] = mapped_column(default=None)
