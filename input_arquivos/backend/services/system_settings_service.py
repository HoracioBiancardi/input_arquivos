"""Serviço de configuração global do MinIO: leitura com fallback pro `.env` e atualização via admin."""

from dataclasses import dataclass

from input_arquivos.backend.config import get_settings
from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.models.system_settings import SystemSettings

_SINGLETON_ID = 1


class MinioConfigIncompleteError(ValueError):
    """Erro levantado ao tentar salvar uma configuração de MinIO sem chave secreta definida."""


@dataclass
class MinioConfig:
    """Configuração do MinIO já resolvida (admin, ou `.env` como fallback), pronta para uso.

    Attributes:
        endpoint: Endereço (host:porta) do servidor MinIO.
        access_key: Chave de acesso do MinIO.
        secret_key: Chave secreta do MinIO.
        secure: Se a conexão com o MinIO deve usar HTTPS.
        source: De onde veio esta configuração ("admin" ou "env"), só para
            a UI indicar a origem — não afeta o comportamento.
    """

    endpoint: str
    access_key: str
    secret_key: str
    secure: bool
    source: str


class SystemSettingsService:
    """Gerencia a configuração global do MinIO (linha única, singleton) cadastrada via `/admin/settings`."""

    def __init__(self, session_factory: DatabaseSessionFactory) -> None:
        """Inicializa o serviço de configurações do sistema.

        Args:
            session_factory: Fábrica de sessões do banco de configuração local.
        """
        self._session_factory = session_factory

    def get_minio_config(self) -> MinioConfig:
        """Resolve a configuração do MinIO a usar: a salva pelo admin, ou o `.env` como fallback.

        Returns:
            Configuração do MinIO, com `source="admin"` se houver uma
            configuração completa salva via admin, ou `source="env"` se a
            aplicação estiver usando os valores do `.env`/`config.py`.
        """
        settings = get_settings()
        with self._session_factory.session() as db_session:
            row = db_session.get(SystemSettings, _SINGLETON_ID)
            if row is not None and row.minio_endpoint and row.minio_access_key and row.minio_secret_key:
                return MinioConfig(
                    endpoint=row.minio_endpoint,
                    access_key=row.minio_access_key,
                    secret_key=row.minio_secret_key,
                    secure=row.minio_secure if row.minio_secure is not None else settings.minio_secure,
                    source="admin",
                )

        return MinioConfig(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            source="env",
        )

    def get_minio_config_for_display(self) -> dict:
        """Monta uma versão da configuração do MinIO segura para retornar pela API.

        Nunca inclui a chave secreta em texto puro — só se ela está
        configurada, para a UI decidir se mostra "chave já configurada" e
        deixar o campo em branco (blank = manter ao salvar de novo).

        Returns:
            Dict com `endpoint`, `access_key`, `secure`,
            `secret_key_configured` (bool) e `source` ("admin" ou "env").
        """
        config = self.get_minio_config()
        return {
            "endpoint": config.endpoint,
            "access_key": config.access_key,
            "secure": config.secure,
            "secret_key_configured": bool(config.secret_key),
            "source": config.source,
        }

    def update_minio_config(self, endpoint: str, access_key: str, secret_key: str | None, secure: bool) -> None:
        """Salva (ou atualiza) a configuração do MinIO cadastrada via admin.

        Args:
            endpoint: Endereço (host:porta) do servidor MinIO.
            access_key: Chave de acesso do MinIO.
            secret_key: Chave secreta do MinIO. Se `None`/vazio e já houver
                uma chave salva, a chave existente é mantida (permite editar
                endpoint/access_key sem redigitar a chave secreta a cada vez).
            secure: Se a conexão com o MinIO deve usar HTTPS.

        Raises:
            MinioConfigIncompleteError: Se não houver `secret_key` informada
                nem uma já salva anteriormente (primeira configuração exige
                a chave secreta).
        """
        with self._session_factory.session() as db_session:
            row = db_session.get(SystemSettings, _SINGLETON_ID)
            if row is None:
                row = SystemSettings(id=_SINGLETON_ID)
                db_session.add(row)

            row.minio_endpoint = endpoint
            row.minio_access_key = access_key
            row.minio_secure = secure
            if secret_key:
                row.minio_secret_key = secret_key

            if not row.minio_secret_key:
                raise MinioConfigIncompleteError("Chave secreta do MinIO é obrigatória na primeira configuração.")

    def clear_minio_config(self) -> None:
        """Remove a configuração salva via admin, voltando a usar o `.env`."""
        with self._session_factory.session() as db_session:
            row = db_session.get(SystemSettings, _SINGLETON_ID)
            if row is not None:
                db_session.delete(row)
