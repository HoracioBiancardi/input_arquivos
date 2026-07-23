"""Criação das tabelas do banco local e cadastro do primeiro usuário admin."""

from sqlalchemy import inspect, select, text

from app.config import get_settings
from app.db.session import DatabaseSessionFactory
from app.models.base import Base
from app.models.context import Context  # noqa: F401 - garante o registro do modelo no metadata
from app.models.upload_history import UploadHistory  # noqa: F401 - garante o registro do modelo no metadata
from app.models.user import User, UserRole
from app.models.user_context_access import user_context_access  # noqa: F401 - garante o registro no metadata
from app.services.auth_service import AuthService


class DatabaseBootstrapper:
    """Prepara o banco de configuração local: cria tabelas e semeia o primeiro admin."""

    def __init__(self, session_factory: DatabaseSessionFactory, auth_service: AuthService) -> None:
        """Inicializa o bootstrapper.

        Args:
            session_factory: Fábrica de sessões do banco de configuração local.
            auth_service: Serviço de autenticação, usado para gerar o hash da senha inicial.
        """
        self._session_factory = session_factory
        self._auth_service = auth_service

    def run(self) -> None:
        """Cria as tabelas (se não existirem), adiciona colunas novas às existentes e semeia o admin."""
        Base.metadata.create_all(self._session_factory.engine)
        self._sync_missing_columns()
        self._seed_first_admin()

    def _sync_missing_columns(self) -> None:
        """Adiciona à força, via `ALTER TABLE`, colunas que o código já conhece mas o banco ainda não tem.

        Este projeto não usa uma ferramenta de migração (Alembic ou similar) —
        o banco local é apenas config/audit de desenvolvimento, então em vez de
        pedir para apagar `data/app_config.db` a cada campo novo adicionado a um
        modelo, o próprio bootstrap detecta colunas faltantes em tabelas já
        existentes e as adiciona (sempre anuláveis, preenchidas com `NULL` nas
        linhas antigas — o código já trata esses campos como opcionais).
        """
        engine = self._session_factory.engine
        inspector = inspect(engine)
        with engine.begin() as connection:
            for table in Base.metadata.sorted_tables:
                if not inspector.has_table(table.name):
                    continue
                existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name in existing_columns:
                        continue
                    column_type = column.type.compile(dialect=engine.dialect)
                    connection.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {column_type}'))

    def _seed_first_admin(self) -> None:
        """Cria o primeiro usuário admin a partir das variáveis de ambiente, se a tabela estiver vazia."""
        settings = get_settings()
        with self._session_factory.session() as db_session:
            existing_user = db_session.execute(select(User).limit(1)).scalar_one_or_none()
            if existing_user is not None:
                return
            admin_user = User(
                username=settings.admin_bootstrap_username,
                password_hash=self._auth_service.hash_password(settings.admin_bootstrap_password),
                role=UserRole.ADMIN,
                active=True,
            )
            db_session.add(admin_user)
