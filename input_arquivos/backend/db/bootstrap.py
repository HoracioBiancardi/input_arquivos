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
from input_arquivos.backend.security import secret_box
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
        self._sync_missing_columns()
        self._seed_first_admin()
        self._encrypt_legacy_plaintext_secrets()

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
                must_change_password=True,
            )
            db_session.add(admin_user)

    def _encrypt_legacy_plaintext_secrets(self) -> None:
        """Re-cifra em repouso segredos gravados em texto puro antes de `EncryptedString` existir.

        `EncryptedString` já trata um valor legado em texto puro como texto
        puro na leitura (não quebra a aplicação para linhas antigas), mas
        sem este passo elas ficariam em texto puro para sempre, a menos que
        um admin editasse o context de novo. Roda a cada startup; idempotente
        (só reescreve a linha se o valor gravado ainda não for um token
        Fernet válido). Usa SQL bruto de propósito, para não disparar a
        cifragem automática do `EncryptedString` duas vezes.
        """
        engine = self._session_factory.engine
        inspector = inspect(engine)
        if not inspector.has_table("contexts"):
            return
        with engine.begin() as connection:
            rows = connection.execute(
                text("SELECT id, db_connection_string FROM contexts WHERE db_connection_string IS NOT NULL")
            ).all()
            for context_id, raw_value in rows:
                if secret_box.is_valid_ciphertext(raw_value):
                    continue
                connection.execute(
                    text("UPDATE contexts SET db_connection_string = :new_value WHERE id = :id"),
                    {"new_value": secret_box.encrypt(raw_value), "id": context_id},
                )
