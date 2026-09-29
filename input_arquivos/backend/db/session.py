"""Engine e fábrica de sessões SQLAlchemy para o banco de configuração local (SQLite)."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from input_arquivos.backend.config import get_settings


_SQLITE_BUSY_TIMEOUT_MS = 10_000


def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    """Prepara cada conexão SQLite para acessos simultâneos.

    Sem WAL, uma gravação bloqueia as leituras, e com vários usuários ao mesmo
    tempo o SQLite devolvia `database is locked`. `busy_timeout` faz a conexão
    esperar a vez em vez de falhar na hora. `synchronous=NORMAL` é o par
    recomendado para WAL (seguro contra corrupção, mais rápido que FULL).

    Args:
        dbapi_connection: Conexão sqlite3 recém-aberta.
        _connection_record: Registro do pool (não usado).
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


class DatabaseSessionFactory:
    """Cria e gerencia o engine SQLAlchemy e as sessões do banco de configuração local."""

    def __init__(self, database_url: str | None = None) -> None:
        """Inicializa a fábrica de sessões.

        Args:
            database_url: URL SQLAlchemy do banco local. Se `None`, é derivada
                de `app_config_db_path` nas configurações da aplicação.
        """
        settings = get_settings()
        settings.app_config_db_path.parent.mkdir(parents=True, exist_ok=True)
        url = database_url or f"sqlite:///{settings.app_config_db_path}"
        self._engine: Engine = create_engine(url, connect_args={"check_same_thread": False})
        if self._engine.dialect.name == "sqlite":
            event.listen(self._engine, "connect", _configure_sqlite_connection)
        self._session_maker: sessionmaker[Session] = sessionmaker(bind=self._engine, expire_on_commit=False)

    @property
    def engine(self) -> Engine:
        """Retorna o engine SQLAlchemy gerenciado por esta fábrica."""
        return self._engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Abre uma sessão SQLAlchemy como context manager, com commit/rollback automáticos.

        Yields:
            Sessão SQLAlchemy pronta para uso.
        """
        db_session = self._session_maker()
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()


_factory: DatabaseSessionFactory | None = None


def get_session_factory() -> DatabaseSessionFactory:
    """Retorna a instância única (singleton) da fábrica de sessões do banco local.

    Returns:
        Instância de `DatabaseSessionFactory` compartilhada por toda a aplicação.
    """
    global _factory
    if _factory is None:
        _factory = DatabaseSessionFactory()
    return _factory
