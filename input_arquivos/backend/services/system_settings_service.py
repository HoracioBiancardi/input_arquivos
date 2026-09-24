"""Serviço de configuração global do MinIO e do SQL Server de destino: leitura (MinIO com fallback pro `.env`) e atualização via admin."""

from dataclasses import dataclass

from sqlalchemy.engine import URL

from input_arquivos.backend.config import get_settings
from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.models.system_settings import SystemSettings

_SINGLETON_ID = 1
DEFAULT_SQLSERVER_PORT = 1433
# Driver fixo: o admin só informa servidor/porta/banco/usuário/senha, nunca a URL —
# então não há como apontar a carga para outro tipo de banco (ex.: `sqlite:///` em disco).
SQLSERVER_DRIVER = "mssql+pymssql"


class MinioConfigIncompleteError(ValueError):
    """Erro levantado ao tentar salvar uma configuração de MinIO sem chave secreta definida."""


class DatabaseConfigIncompleteError(ValueError):
    """Erro levantado ao salvar/testar a conexão do banco de destino sem senha definida."""


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


@dataclass
class DatabaseConfig:
    """Conexão do SQL Server de destino da carga de tabelas.

    Attributes:
        host: Servidor (hostname ou IP).
        port: Porta do SQL Server.
        database: Nome do banco de dados.
        username: Usuário do SQL Server.
        password: Senha do SQL Server.
    """

    host: str
    port: int
    database: str
    username: str
    password: str

    def to_url(self) -> URL:
        """Monta a URL SQLAlchemy da conexão.

        `URL.create` recebe cada parte separada e escapa os caracteres
        especiais (`@`, `:`, `/`, `%`) de usuário e senha — montar a string à
        mão quebraria a conexão com uma senha como `S3nh@/forte`.

        Returns:
            URL pronta para `create_engine`.
        """
        return URL.create(
            SQLSERVER_DRIVER,
            username=self.username,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.database,
        )


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
        """Remove a configuração do MinIO salva via admin, voltando a usar o `.env`.

        Só limpa os campos do MinIO — a linha singleton também guarda a
        conexão do SQL Server de destino, que não deve ser perdida junto.
        """
        with self._session_factory.session() as db_session:
            row = db_session.get(SystemSettings, _SINGLETON_ID)
            if row is not None:
                row.minio_endpoint = None
                row.minio_access_key = None
                row.minio_secret_key = None
                row.minio_secure = None

    def get_database_config(self) -> DatabaseConfig | None:
        """Retorna a conexão do SQL Server de destino, se configurada por completo.

        Returns:
            Configuração com todos os campos preenchidos, ou `None` se ainda
            não houver conexão salva.
        """
        with self._session_factory.session() as db_session:
            row = db_session.get(SystemSettings, _SINGLETON_ID)
            if row is None or not (row.db_host and row.db_name and row.db_username and row.db_password):
                return None
            return DatabaseConfig(
                host=row.db_host,
                port=row.db_port or DEFAULT_SQLSERVER_PORT,
                database=row.db_name,
                username=row.db_username,
                password=row.db_password,
            )

    def get_database_url(self) -> URL | None:
        """Monta a URL SQLAlchemy da conexão salva, usada pelo `DatabaseLoader`.

        Returns:
            URL pronta para `create_engine`, ou `None` se não configurada.
        """
        config = self.get_database_config()
        return config.to_url() if config is not None else None

    def get_database_config_for_display(self) -> dict:
        """Monta uma versão da conexão do banco de destino segura para retornar pela API.

        Nunca inclui a senha — só se ela está configurada, para a UI mostrar
        "senha já configurada" e aceitar o campo em branco ao salvar de novo.

        Returns:
            Dict com `configured`, `host`, `port`, `database`, `username` e
            `password_configured`.
        """
        with self._session_factory.session() as db_session:
            row = db_session.get(SystemSettings, _SINGLETON_ID)
            if row is None:
                row = SystemSettings(id=_SINGLETON_ID)
            return {
                "configured": bool(row.db_host and row.db_name and row.db_username and row.db_password),
                "host": row.db_host,
                "port": row.db_port or DEFAULT_SQLSERVER_PORT,
                "database": row.db_name,
                "username": row.db_username,
                "password_configured": bool(row.db_password),
            }

    def update_database_config(
        self, host: str, port: int, database: str, username: str, password: str | None
    ) -> None:
        """Salva (ou atualiza) a conexão do SQL Server de destino.

        Args:
            host: Servidor (hostname ou IP).
            port: Porta do SQL Server.
            database: Nome do banco de dados.
            username: Usuário do SQL Server.
            password: Senha. Se `None`/vazia e já houver uma salva, a senha
                existente é mantida (permite editar os outros campos sem
                redigitá-la).

        Raises:
            DatabaseConfigIncompleteError: Se não houver senha informada nem
                uma já salva anteriormente.
        """
        with self._session_factory.session() as db_session:
            row = db_session.get(SystemSettings, _SINGLETON_ID)
            if row is None:
                row = SystemSettings(id=_SINGLETON_ID)
                db_session.add(row)

            row.db_host = host
            row.db_port = port
            row.db_name = database
            row.db_username = username
            if password:
                row.db_password = password

            if not row.db_password:
                raise DatabaseConfigIncompleteError("Senha do banco é obrigatória na primeira configuração.")

    def resolve_database_config(
        self, host: str, port: int, database: str, username: str, password: str | None
    ) -> DatabaseConfig:
        """Monta uma configuração a testar a partir do formulário, completando a senha com a já salva.

        Args:
            host: Servidor (hostname ou IP).
            port: Porta do SQL Server.
            database: Nome do banco de dados.
            username: Usuário do SQL Server.
            password: Senha digitada; vazia usa a senha já salva.

        Returns:
            Configuração pronta para testar.

        Raises:
            DatabaseConfigIncompleteError: Se não houver senha digitada nem salva.
        """
        if not password:
            with self._session_factory.session() as db_session:
                row = db_session.get(SystemSettings, _SINGLETON_ID)
                password = row.db_password if row is not None else None
        if not password:
            raise DatabaseConfigIncompleteError("Informe a senha do banco para testar.")
        return DatabaseConfig(host=host, port=port, database=database, username=username, password=password)

    def clear_database_config(self) -> None:
        """Remove a conexão do banco de destino (contexts com carga ligada passam a registrar erro de carga)."""
        with self._session_factory.session() as db_session:
            row = db_session.get(SystemSettings, _SINGLETON_ID)
            if row is not None:
                row.db_host = None
                row.db_port = None
                row.db_name = None
                row.db_username = None
                row.db_password = None
