"""Criação das tabelas do banco local e cadastro do primeiro usuário admin."""

from sqlalchemy import inspect, select, text

from input_arquivos.backend.config import get_settings
from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.models.base import Base
from input_arquivos.backend.models.context import Context  # noqa: F401 - garante o registro do modelo no metadata
from input_arquivos.backend.models.system_settings import SystemSettings  # noqa: F401 - garante o registro do modelo no metadata
from input_arquivos.backend.models.upload_history import UploadHistory  # noqa: F401 - garante o registro do modelo no metadata
from input_arquivos.backend.models.user import User, UserRole
from input_arquivos.backend.models.user_context_access import user_context_access  # noqa: F401 - garante o registro no metadata
from input_arquivos.backend.services.auth_service import AuthService


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
        self._drop_legacy_required_columns()
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

    def _drop_legacy_required_columns(self) -> None:
        """Reconstrói tabelas que ainda têm colunas antigas obrigatórias que o código não conhece mais.

        Bancos criados por versões antigas guardam colunas removidas do modelo (ex.: `contexts.
        db_schema_name`, `default_write_mode`) como `NOT NULL` sem valor padrão: todo INSERT novo
        falha (o app mostrava "Já existe um registro com esses dados"). O SQLite não altera nem
        remove coluna com restrição, então a tabela é recriada pelo modelo atual e os dados das
        colunas em comum são copiados. `legacy_alter_table` evita que o RENAME reescreva as chaves
        estrangeiras das outras tabelas para a cópia temporária.
        """
        engine = self._session_factory.engine
        inspector = inspect(engine)
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            known = {column.name for column in table.columns}
            existing = inspector.get_columns(table.name)
            blocking = [
                c["name"] for c in existing
                if c["name"] not in known and not c.get("nullable", True) and c.get("default") is None
            ]
            if not blocking:
                continue
            common = [c["name"] for c in existing if c["name"] in known]
            cols = ", ".join(f'"{name}"' for name in common)
            old = f"{table.name}__antiga"
            indexes = [i["name"] for i in inspector.get_indexes(table.name) if i.get("name")]
            with engine.begin() as connection:
                connection.execute(text("PRAGMA foreign_keys=OFF"))
                for name in indexes:  # recriados com o mesmo nome pelo modelo
                    connection.execute(text(f'DROP INDEX IF EXISTS "{name}"'))
                connection.execute(text("PRAGMA legacy_alter_table=ON"))
                connection.execute(text(f'ALTER TABLE "{table.name}" RENAME TO "{old}"'))
                table.create(connection)
                connection.execute(text(f'INSERT INTO "{table.name}" ({cols}) SELECT {cols} FROM "{old}"'))
                connection.execute(text(f'DROP TABLE "{old}"'))
                connection.execute(text("PRAGMA legacy_alter_table=OFF"))
                connection.execute(text("PRAGMA foreign_keys=ON"))

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
                must_change_password=True,
            )
            db_session.add(admin_user)
