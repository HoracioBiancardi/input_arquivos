"""Serviço que orquestra o pipeline de ingestão, o destination writer e o registro de auditoria."""

from datetime import date

from sqlalchemy import select

from app.db.session import DatabaseSessionFactory
from app.destinations.registry import DestinationWriterRegistry
from app.ingestion.pipeline import IngestionPipeline, IngestResult
from app.models.context import Context, WriteMode
from app.models.upload_history import UploadHistory, UploadStatus
from app.services.column_check import (
    ColumnMismatch,
    ColumnMismatchChecker,
    RequiredColumnChecker,
    RequiredColumnViolation,
)
from app.services.context_service import ContextService


class ContextNotFoundError(ValueError):
    """Erro levantado quando o contexto informado não existe ou está inativo."""


class UploadService:
    """Processa um upload de ponta a ponta: ingestão, escrita no destino e auditoria."""

    def __init__(
        self,
        session_factory: DatabaseSessionFactory,
        context_service: ContextService,
        pipeline: IngestionPipeline,
        writer_registry: DestinationWriterRegistry,
    ) -> None:
        """Inicializa o serviço de upload.

        Args:
            session_factory: Fábrica de sessões do banco de configuração local.
            context_service: Serviço usado para resolver o contexto pelo nome.
            pipeline: Pipeline de ingestão (leitura + conversão para Parquet).
            writer_registry: Registro de destination writers disponíveis.
        """
        self._session_factory = session_factory
        self._context_service = context_service
        self._pipeline = pipeline
        self._writer_registry = writer_registry
        self._column_checker = ColumnMismatchChecker()
        self._required_column_checker = RequiredColumnChecker()

    def resolve_context(self, context_name: str) -> Context:
        """Busca um contexto ativo pelo nome.

        Args:
            context_name: Nome do contexto selecionado pelo usuário.

        Returns:
            O contexto encontrado.

        Raises:
            ContextNotFoundError: Se o contexto não existir ou estiver inativo.
        """
        context = self._context_service.get_by_name(context_name)
        if context is None or not context.active:
            raise ContextNotFoundError(f"Context '{context_name}' não existe ou está inativo.")
        return context

    def build_artifact(self, file_bytes: bytes, filename: str, context: Context, uploaded_by: str) -> IngestResult:
        """Lê e transforma o arquivo enviado, sem gravar em nenhum destino ainda.

        Usado pelo fluxo interativo da tela de upload, que precisa inspecionar
        as colunas do arquivo (via `check_column_mismatch`) antes de decidir
        se grava no destino ou pede confirmação ao usuário.

        Args:
            file_bytes: Conteúdo bruto do arquivo enviado.
            filename: Nome original do arquivo.
            context: Contexto selecionado pelo usuário.
            uploaded_by: Nome do usuário autenticado que realizou o upload.

        Returns:
            O artefato pronto para ser gravado por `finalize`.
        """
        return self._pipeline.process(file_bytes, filename, context, uploaded_by)

    def check_column_mismatch(self, context: Context, artifact: IngestResult) -> ColumnMismatch | None:
        """Verifica se as colunas do artefato divergem das colunas já aceitas para o contexto.

        Args:
            context: Contexto selecionado pelo usuário.
            artifact: Artefato produzido por `build_artifact`.

        Returns:
            Um `ColumnMismatch` se houver divergência a confirmar, ou `None`
            se as colunas baterem, for o primeiro upload do contexto, ou o
            artefato não tiver um DataFrame associado (ex.: PDF em modo raw_archive).
        """
        if artifact.dataframe is None:
            return None
        return self._column_checker.check(context, artifact.dataframe)

    def check_required_columns(self, context: Context, artifact: IngestResult) -> RequiredColumnViolation | None:
        """Verifica se as colunas obrigatórias do contexto vieram preenchidas no artefato.

        Args:
            context: Contexto selecionado pelo usuário.
            artifact: Artefato produzido por `build_artifact`.

        Returns:
            Um `RequiredColumnViolation` se alguma coluna obrigatória estiver
            ausente ou vazia, ou `None` se o contexto não tiver colunas
            obrigatórias configuradas, todas estiverem preenchidas, ou o
            artefato não tiver um DataFrame associado (ex.: PDF em modo raw_archive).
        """
        if artifact.dataframe is None:
            return None
        return self._required_column_checker.check(context, artifact.dataframe)

    def finalize(
        self,
        artifact: IngestResult,
        context: Context,
        write_mode: WriteMode | None,
        filename: str,
        uploaded_by: str,
    ) -> UploadHistory:
        """Grava o artefato no destino do contexto e registra o resultado no audit log.

        Em caso de sucesso, também atualiza `context.expected_columns` com as
        colunas deste upload, para que os próximos envios sejam comparados
        contra elas.

        Args:
            artifact: Artefato já construído por `build_artifact`.
            context: Contexto de destino.
            write_mode: Modo de escrita escolhido (relevante só para destinos de banco).
            filename: Nome original do arquivo, para o registro de auditoria.
            uploaded_by: Nome do usuário autenticado que realizou o upload.

        Returns:
            O registro de `UploadHistory` criado, já persistido.
        """
        try:
            writer = self._writer_registry.get(context.destination_type)
            result = writer.write(artifact, context, write_mode)
            history = UploadHistory(
                filename=filename,
                context_name=context.name,
                destination_type=context.destination_type,
                destination_detail=result.destination_detail,
                write_mode=write_mode,
                status=UploadStatus.SUCCESS,
                row_count=result.row_count,
                error_message=None,
                uploaded_by=uploaded_by,
            )
            if artifact.dataframe is not None:
                self._context_service.update(
                    context.id, expected_columns=self._column_checker.serialize(artifact.dataframe)
                )
        except Exception as error:  # noqa: BLE001 - qualquer falha vira um registro de auditoria com erro
            history = UploadHistory(
                filename=filename,
                context_name=context.name,
                destination_type=context.destination_type,
                destination_detail="",
                write_mode=write_mode,
                status=UploadStatus.ERROR,
                row_count=None,
                error_message=str(error),
                uploaded_by=uploaded_by,
            )

        return self._persist_history(history)

    def process_upload(
        self,
        file_bytes: bytes,
        filename: str,
        context_name: str,
        write_mode: WriteMode | None,
        uploaded_by: str,
    ) -> UploadHistory:
        """Processa um arquivo enviado de ponta a ponta e registra o resultado no audit log.

        Usado pela API REST, onde não há um humano para confirmar divergências
        de colunas — a leitura, a escrita no destino e a auditoria acontecem
        em uma única chamada. Nunca propaga exceções ao chamador: qualquer
        falha durante a ingestão ou a escrita no destino é capturada e
        registrada como um `UploadHistory` com `status=ERROR`.

        Args:
            file_bytes: Conteúdo bruto do arquivo enviado.
            filename: Nome original do arquivo.
            context_name: Nome do contexto selecionado pelo usuário.
            write_mode: Modo de escrita escolhido (relevante só para destinos de banco).
            uploaded_by: Nome do usuário autenticado que realizou o upload.

        Returns:
            O registro de `UploadHistory` criado, já persistido.

        Raises:
            ContextNotFoundError: Se o contexto não existir ou estiver inativo.
        """
        context = self.resolve_context(context_name)
        try:
            artifact = self.build_artifact(file_bytes, filename, context, uploaded_by)
        except Exception as error:  # noqa: BLE001 - qualquer falha vira um registro de auditoria com erro
            return self.record_error(context, filename, write_mode, uploaded_by, str(error))

        return self.finalize(artifact, context, write_mode, filename, uploaded_by)

    def record_error(
        self, context: Context, filename: str, write_mode: WriteMode | None, uploaded_by: str, error_message: str
    ) -> UploadHistory:
        """Registra no audit log uma tentativa de upload que falhou antes de gravar em qualquer destino.

        Usado quando a leitura/conversão do arquivo falha (ex.: extensão não
        suportada, PDF corrompido) ou quando o usuário cancela um upload após
        ver um aviso de colunas divergentes.

        Args:
            context: Contexto selecionado pelo usuário.
            filename: Nome original do arquivo.
            write_mode: Modo de escrita escolhido, se aplicável.
            uploaded_by: Nome do usuário autenticado que realizou o upload.
            error_message: Mensagem descrevendo o motivo da falha/cancelamento.

        Returns:
            O registro de `UploadHistory` criado, já persistido.
        """
        history = UploadHistory(
            filename=filename,
            context_name=context.name,
            destination_type=context.destination_type,
            destination_detail="",
            write_mode=write_mode,
            status=UploadStatus.ERROR,
            row_count=None,
            error_message=error_message,
            uploaded_by=uploaded_by,
        )
        return self._persist_history(history)

    def _persist_history(self, history: UploadHistory) -> UploadHistory:
        """Persiste um registro de `UploadHistory` no banco de configuração local.

        Args:
            history: Registro a persistir.

        Returns:
            O mesmo registro, já com `id` preenchido pelo banco.
        """
        with self._session_factory.session() as db_session:
            db_session.add(history)
            db_session.flush()
            db_session.refresh(history)
            db_session.expunge(history)
        return history

    def list_recent(self, limit: int = 20) -> list[UploadHistory]:
        """Lista os uploads mais recentes, para exibição na tela principal.

        Args:
            limit: Quantidade máxima de registros a retornar.

        Returns:
            Lista de `UploadHistory` ordenada do mais recente para o mais antigo.
        """
        with self._session_factory.session() as db_session:
            return list(
                db_session.execute(
                    select(UploadHistory).order_by(UploadHistory.created_at.desc()).limit(limit)
                ).scalars().all()
            )

    def list_filtered(
        self,
        context_name: str | None = None,
        status: UploadStatus | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 200,
    ) -> list[UploadHistory]:
        """Lista uploads filtrados por contexto, status e período, para a tela de audit log.

        Args:
            context_name: Filtra por nome de contexto, se informado.
            status: Filtra por status (sucesso/erro), se informado.
            start_date: Data inicial (inclusive) do período, se informado.
            end_date: Data final (inclusive) do período, se informado.
            limit: Quantidade máxima de registros a retornar.

        Returns:
            Lista de `UploadHistory` ordenada do mais recente para o mais antigo.
        """
        query = select(UploadHistory)
        if context_name:
            query = query.where(UploadHistory.context_name == context_name)
        if status:
            query = query.where(UploadHistory.status == status)
        if start_date:
            query = query.where(UploadHistory.created_at >= start_date)
        if end_date:
            query = query.where(UploadHistory.created_at <= end_date)
        query = query.order_by(UploadHistory.created_at.desc()).limit(limit)

        with self._session_factory.session() as db_session:
            return list(db_session.execute(query).scalars().all())
