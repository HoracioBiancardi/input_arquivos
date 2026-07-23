"""Serviço de CRUD de contexts e verificação de conectividade com seus destinos."""

from dataclasses import dataclass
from pathlib import Path

from minio import Minio
from sqlalchemy import create_engine, select, text

from app.config import get_settings
from app.db.session import DatabaseSessionFactory
from app.models.context import Context, DestinationType, PdfMode, WriteMode


@dataclass
class ConnectionTestResult:
    """Resultado de um teste de conectividade com um destino (MinIO ou banco de dados).

    Attributes:
        success: Se a conexão foi bem-sucedida.
        message: Mensagem amigável descrevendo o resultado do teste.
    """

    success: bool
    message: str


class ContextService:
    """Gerencia o CRUD de contexts e os testes de conectividade com seus destinos."""

    def __init__(self, session_factory: DatabaseSessionFactory) -> None:
        """Inicializa o serviço de contexts.

        Args:
            session_factory: Fábrica de sessões do banco de configuração local.
        """
        self._session_factory = session_factory

    def list_all(self) -> list[Context]:
        """Lista todos os contexts cadastrados, ativos ou não.

        Returns:
            Lista de contexts ordenada por nome.
        """
        with self._session_factory.session() as db_session:
            return list(db_session.execute(select(Context).order_by(Context.name)).scalars().all())

    def list_active(self) -> list[Context]:
        """Lista apenas os contexts ativos, usados no seletor da tela de upload.

        Returns:
            Lista de contexts ativos ordenada por nome.
        """
        with self._session_factory.session() as db_session:
            return list(
                db_session.execute(
                    select(Context).where(Context.active.is_(True)).order_by(Context.name)
                ).scalars().all()
            )

    def get_by_id(self, context_id: int) -> Context | None:
        """Busca um context pelo identificador interno.

        Args:
            context_id: Identificador do context.

        Returns:
            O context encontrado, ou `None` se não existir.
        """
        with self._session_factory.session() as db_session:
            return db_session.get(Context, context_id)

    def get_by_name(self, name: str) -> Context | None:
        """Busca um context pelo nome único.

        Args:
            name: Nome do context.

        Returns:
            O context encontrado, ou `None` se não existir.
        """
        with self._session_factory.session() as db_session:
            return db_session.execute(select(Context).where(Context.name == name)).scalar_one_or_none()

    def create(
        self,
        name: str,
        destination_type: DestinationType,
        default_write_mode: WriteMode,
        pdf_mode: PdfMode,
        minio_bucket: str | None = None,
        db_connection_string: str | None = None,
        db_schema_name: str = "dbo",
        db_table: str | None = None,
        local_path: str | None = None,
        allowed_file_types: str = "excel,csv,pdf",
    ) -> Context:
        """Cria um novo context.

        Args:
            name: Nome único do context.
            destination_type: Tipo de destino (MinIO, SQL Server ou pasta local).
            default_write_mode: Modo de escrita pré-selecionado na tela de upload.
            pdf_mode: Modo de tratamento de PDFs para este context.
            minio_bucket: Nome do bucket, quando `destination_type` é MINIO.
            db_connection_string: URL de conexão do banco, quando `destination_type` é SQLSERVER.
            db_schema_name: Schema da tabela de destino.
            db_table: Nome da tabela de destino.
            local_path: Pasta no disco local, quando `destination_type` é LOCAL.
            allowed_file_types: Tipos de arquivo aceitos (valores de `FileType`
                separados por vírgula, ex. "excel,csv").

        Returns:
            O context recém-criado.
        """
        context = Context(
            name=name,
            destination_type=destination_type,
            default_write_mode=default_write_mode,
            pdf_mode=pdf_mode,
            minio_bucket=minio_bucket,
            db_connection_string=db_connection_string,
            db_schema_name=db_schema_name,
            db_table=db_table,
            local_path=local_path,
            allowed_file_types=allowed_file_types,
        )
        with self._session_factory.session() as db_session:
            db_session.add(context)
            db_session.flush()
            db_session.refresh(context)
            db_session.expunge(context)
        return context

    def update(self, context_id: int, **fields: object) -> Context | None:
        """Atualiza campos de um context existente.

        Args:
            context_id: Identificador do context a atualizar.
            **fields: Campos e novos valores a aplicar no context.

        Returns:
            O context atualizado, ou `None` se não existir.
        """
        with self._session_factory.session() as db_session:
            context = db_session.get(Context, context_id)
            if context is None:
                return None
            for field_name, value in fields.items():
                setattr(context, field_name, value)
            db_session.flush()
            db_session.refresh(context)
            db_session.expunge(context)
            return context

    def set_active(self, context_id: int, active: bool) -> None:
        """Ativa ou desativa um context.

        Args:
            context_id: Identificador do context.
            active: Novo estado de ativação.
        """
        self.update(context_id, active=active)

    def test_minio_connection(self, bucket: str) -> ConnectionTestResult:
        """Testa a conectividade com um bucket no servidor MinIO configurado globalmente.

        O endpoint e as credenciais do MinIO são compartilhados por todos os
        contexts (vêm das configurações da aplicação); apenas o bucket varia
        por context.

        Args:
            bucket: Nome do bucket a verificar/criar.

        Returns:
            Resultado do teste de conectividade.
        """
        settings = get_settings()
        try:
            client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
                return ConnectionTestResult(True, f"Conectado com sucesso. Bucket '{bucket}' criado.")
            return ConnectionTestResult(True, f"Conectado com sucesso. Bucket '{bucket}' já existe.")
        except Exception as error:  # noqa: BLE001 - erro de conectividade externo, reportado ao usuário
            return ConnectionTestResult(False, f"Falha ao conectar no MinIO: {error}")

    def test_db_connection(self, connection_string: str) -> ConnectionTestResult:
        """Testa a conectividade com o banco de dados de destino executando um SELECT simples.

        Args:
            connection_string: URL de conexão SQLAlchemy do banco de destino.

        Returns:
            Resultado do teste de conectividade.
        """
        try:
            engine = create_engine(connection_string)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return ConnectionTestResult(True, "Conexão com o banco de dados estabelecida com sucesso.")
        except Exception as error:  # noqa: BLE001 - erro de conectividade externo, reportado ao usuário
            return ConnectionTestResult(False, f"Falha ao conectar no banco de dados: {error}")

    def test_local_path(self, path: str) -> ConnectionTestResult:
        """Testa se a pasta local de destino pode ser criada e é gravável.

        Útil para contexts do tipo "local", usados para testar o sistema por
        completo sem depender de um MinIO/SQL Server externo.

        Args:
            path: Caminho da pasta local a verificar/criar.

        Returns:
            Resultado do teste de conectividade.
        """
        try:
            folder = Path(path)
            folder.mkdir(parents=True, exist_ok=True)
            probe_file = folder / ".write_test"
            probe_file.write_text("ok")
            probe_file.unlink()
            return ConnectionTestResult(True, f"Pasta '{folder.resolve()}' criada/acessível e gravável.")
        except Exception as error:  # noqa: BLE001 - erro de I/O reportado ao usuário
            return ConnectionTestResult(False, f"Falha ao acessar a pasta local: {error}")
