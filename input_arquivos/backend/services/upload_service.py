"""Serviço que orquestra o pipeline de ingestão, o destination writer, a carga no banco e o registro de auditoria."""

from datetime import date, datetime, timezone

from sqlalchemy import select, update

from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.destinations.artifact_reader import read_artifact_bytes
from input_arquivos.backend.destinations.registry import DestinationWriterRegistry
from input_arquivos.backend.ingestion.pipeline import IngestionPipeline, IngestResult
from input_arquivos.backend.loaders.database_loader import DatabaseLoader, DatabaseNotConfiguredError
from input_arquivos.backend.models.context import Context, DuplicatePolicy
from input_arquivos.backend.models.upload_history import LoadStatus, UploadHistory, UploadStatus
from input_arquivos.backend.services.column_check import (
    ColumnDataValidator,
    ColumnDataViolation,
    ColumnMismatch,
    ColumnMismatchChecker,
)
from input_arquivos.backend.services.context_service import ContextService
from input_arquivos.backend.services.period import PeriodError, format_date_br, is_monthly, period_label, resolve_period


class ContextNotFoundError(ValueError):
    """Erro levantado quando o contexto informado não existe ou está inativo."""


class UploadNotFoundError(ValueError):
    """Erro levantado quando o `UploadHistory` informado não existe."""


class LoadNotApplicableError(ValueError):
    """Erro levantado ao pedir a carga no banco de um upload que não pode ser carregado."""


class PeriodAlreadySentError(ValueError):
    """Erro levantado quando o mês já tem envio vigente e o reenvio não foi confirmado.

    Attributes:
        current: O envio vigente daquele mês.
    """

    def __init__(self, message: str, current: UploadHistory) -> None:
        super().__init__(message)
        self.current = current


def describe_current_upload(current: UploadHistory) -> str:
    """Resumo de quem enviou o mês e quando, para as mensagens de mês repetido."""
    return f"{period_label(current.period)} já foi enviado por {current.uploaded_by} em {format_date_br(current.created_at)}"


class UploadService:
    """Processa um upload de ponta a ponta: ingestão, escrita no destino, carga no banco e auditoria."""

    def __init__(
        self,
        session_factory: DatabaseSessionFactory,
        context_service: ContextService,
        pipeline: IngestionPipeline,
        writer_registry: DestinationWriterRegistry,
        database_loader: DatabaseLoader | None = None,
    ) -> None:
        """Inicializa o serviço de upload.

        Args:
            session_factory: Fábrica de sessões do banco de configuração local.
            context_service: Serviço usado para resolver o contexto pelo nome.
            pipeline: Pipeline de ingestão (leitura + conversão para Parquet).
            writer_registry: Registro de destination writers disponíveis.
            database_loader: Loader que carrega o Parquet na tabela do
                contexto no banco de destino. `None` faz toda carga pedida
                falhar com "banco não configurado".
        """
        self._session_factory = session_factory
        self._context_service = context_service
        self._pipeline = pipeline
        self._writer_registry = writer_registry
        self._database_loader = database_loader
        self._column_checker = ColumnMismatchChecker()
        self._column_data_validator = ColumnDataValidator()

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

    def check_column_data(self, context: Context, artifact: IngestResult) -> ColumnDataViolation | None:
        """Verifica se os dados de cada coluna do artefato respeitam as regras de validação do contexto.

        Args:
            context: Contexto selecionado pelo usuário.
            artifact: Artefato produzido por `build_artifact`.

        Returns:
            Um `ColumnDataViolation` se alguma célula violar uma regra de tipo
            ou obrigatoriedade configurada em `context.column_rules`, ou
            `None` se o contexto não tiver regras, tudo passar, ou o
            artefato não tiver um DataFrame associado (ex.: PDF em modo raw_archive).
        """
        if artifact.dataframe is None:
            return None
        return self._column_data_validator.check(context, artifact.dataframe)

    def describe_column_data_violation(self, violation: ColumnDataViolation) -> str:
        """Monta um resumo textual das violações de dados encontradas, para o audit log.

        Args:
            violation: Violação retornada por `check_column_data`.

        Returns:
            Mensagem legível descrevendo cada coluna e motivo de rejeição.
        """
        reason_labels = {
            "coluna_ausente": "coluna ausente",
            "obrigatoria": "célula obrigatória vazia",
            "tipo_invalido": "tipo inválido",
        }
        parts = [
            f"{detail.column} ({reason_labels.get(detail.reason, detail.reason)}, {detail.bad_row_count} linha(s))"
            for detail in violation.details
        ]
        return "Dados inválidos: " + "; ".join(parts)

    def apply_period(
        self, context: Context, artifact: IngestResult, informed_period: str | None
    ) -> tuple[IngestResult, str | None]:
        """Descobre o mês de competência do envio e o grava no artefato (coluna `competencia_envio`).

        Args:
            context: Contexto do envio.
            artifact: Artefato produzido por `build_artifact`.
            informed_period: Mês escolhido pelo usuário (`AAAA-MM`), quando o
                contexto pede o mês no envio.

        Returns:
            O artefato (com a coluna de mês, se tiver tabela) e o mês; o
            artefato sem mudança e `None` se o contexto não é mensal.

        Raises:
            PeriodError: Se o mês não puder ser determinado (ver `resolve_period`).
        """
        period = resolve_period(context, artifact.dataframe, informed_period)
        if period is None:
            return artifact, None
        return self._pipeline.with_period(artifact, context, period), period

    def find_current_upload(self, context: Context, period: str | None) -> UploadHistory | None:
        """Busca o envio vigente (com sucesso e não substituído) de um mês, se o reenvio importa.

        Args:
            context: Contexto do envio.
            period: Mês do envio (`None` em contexto sem controle por mês).

        Returns:
            O envio vigente do mês, ou `None` se não houver, se o contexto não
            for mensal ou se a política do contexto permite meses repetidos.
        """
        if period is None or (context.duplicate_policy or DuplicatePolicy.REPLACE) == DuplicatePolicy.ALLOW:
            return None
        query = (
            select(UploadHistory)
            .where(
                UploadHistory.context_name == context.name,
                UploadHistory.period == period,
                UploadHistory.status == UploadStatus.SUCCESS,
                UploadHistory.superseded_by.is_(None),
            )
            .order_by(UploadHistory.id.desc())
            .limit(1)
        )
        with self._session_factory.session() as db_session:
            current = db_session.execute(query).scalar_one_or_none()
            if current is not None:
                db_session.expunge(current)
            return current

    def finalize(
        self,
        artifact: IngestResult,
        context: Context,
        filename: str,
        uploaded_by: str,
        period: str | None = None,
    ) -> UploadHistory:
        """Grava o artefato no destino do contexto e registra o resultado no audit log.

        Em caso de sucesso, também atualiza `context.expected_columns` com as
        colunas deste upload, para que os próximos envios sejam comparados
        contra elas. Se o contexto carrega no banco e o artefato é um
        Parquet, o registro sai com `load_status=PENDING` — a carga em si é
        feita depois por `run_database_load`, para que uma falha no banco
        nunca desfaça o upload já gravado no MinIO.

        Com `period`, o envio vigente anterior do mesmo mês (se houver, e se a
        política do contexto não for "permitir") passa a apontar para este em
        `superseded_by` — as linhas dele saem da tabela na carga deste.

        Args:
            artifact: Artefato já construído por `build_artifact`.
            context: Contexto de destino.
            filename: Nome original do arquivo, para o registro de auditoria.
            uploaded_by: Nome do usuário autenticado que realizou o upload.
            period: Mês de competência (`AAAA-MM`), em contextos mensais.

        Returns:
            O registro de `UploadHistory` criado, já persistido.
        """
        try:
            writer = self._writer_registry.get(context.destination_type)
            result = writer.write(artifact, context)
            history = UploadHistory(
                filename=filename,
                context_name=context.name,
                destination_type=context.destination_type,
                destination_detail=result.destination_detail,
                status=UploadStatus.SUCCESS,
                artifact_kind=artifact.artifact_kind,
                row_count=result.row_count,
                error_message=None,
                load_status=LoadStatus.PENDING if self._should_load(context, artifact) else None,
                period=period,
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
                status=UploadStatus.ERROR,
                row_count=None,
                error_message="Não foi possível gravar o arquivo no destino do contexto. Avise o administrador.",
                error_detail=str(error),
                period=period,
                uploaded_by=uploaded_by,
            )

        if history.status == UploadStatus.SUCCESS and period is not None:
            return self._persist_superseding(history, context)
        return self._persist_history(history)

    def _persist_superseding(self, history: UploadHistory, context: Context) -> UploadHistory:
        """Grava um envio com mês e, na mesma transação, marca o(s) anterior(es) do mês como substituídos.

        Com a política "permitir", nada é substituído (os envios do mês se somam).
        """
        with self._session_factory.session() as db_session:
            db_session.add(history)
            db_session.flush()
            if (context.duplicate_policy or DuplicatePolicy.REPLACE) != DuplicatePolicy.ALLOW:
                previous = (
                    UploadHistory.context_name == history.context_name,
                    UploadHistory.period == history.period,
                    UploadHistory.status == UploadStatus.SUCCESS,
                    UploadHistory.superseded_by.is_(None),
                    UploadHistory.id != history.id,
                )
                db_session.execute(update(UploadHistory).where(*previous).values(superseded_by=history.id))
                db_session.execute(
                    update(UploadHistory)
                    .where(UploadHistory.superseded_by == history.id, UploadHistory.load_status.is_not(None))
                    .values(load_status=LoadStatus.SUPERSEDED, load_error=None)
                )
            db_session.refresh(history)
            db_session.expunge(history)
        return history

    def process_upload(
        self,
        file_bytes: bytes,
        filename: str,
        context_name: str,
        uploaded_by: str,
        period: str | None = None,
        replace_period: bool = False,
    ) -> UploadHistory:
        """Processa um arquivo enviado de ponta a ponta e registra o resultado no audit log.

        Usado pela API REST, onde não há um humano para confirmar divergências
        de colunas — a leitura, a escrita no destino, a carga no banco (se o
        contexto pedir) e a auditoria acontecem em uma única chamada. Falhas
        de ingestão, de mês de competência e de escrita no destino não são
        propagadas: viram um `UploadHistory` com `status=ERROR`.

        Args:
            file_bytes: Conteúdo bruto do arquivo enviado.
            filename: Nome original do arquivo.
            context_name: Nome do contexto selecionado pelo usuário.
            uploaded_by: Nome do usuário autenticado que realizou o upload.
            period: Mês de competência (`AAAA-MM`), quando o contexto pede o mês no envio.
            replace_period: Confirma a substituição de um mês que já tem envio.

        Returns:
            O registro de `UploadHistory` criado, já persistido.

        Raises:
            ContextNotFoundError: Se o contexto não existir ou estiver inativo.
            PeriodAlreadySentError: Se o mês já tem envio, a política do
                contexto é substituir e `replace_period` não foi enviado.
        """
        context = self.resolve_context(context_name)
        try:
            artifact = self.build_artifact(file_bytes, filename, context, uploaded_by)
        except Exception as error:  # noqa: BLE001 - qualquer falha vira um registro de auditoria com erro
            return self.record_error(context, filename, uploaded_by, str(error))

        violation = self.check_column_data(context, artifact)
        if violation is not None:
            return self.record_error(
                context, filename, uploaded_by, self.describe_column_data_violation(violation)
            )

        try:
            artifact, resolved_period = self.apply_period(context, artifact, period)
        except PeriodError as error:
            return self.record_error(context, filename, uploaded_by, str(error))

        current = self.find_current_upload(context, resolved_period)
        if current is not None:
            if context.duplicate_policy == DuplicatePolicy.BLOCK:
                return self.record_error(context, filename, uploaded_by, self.describe_blocked_period(current))
            if not replace_period:
                raise PeriodAlreadySentError(f"{describe_current_upload(current)}. Confirme a substituição.", current)

        history = self.finalize(artifact, context, filename, uploaded_by, resolved_period)
        if history.load_status == LoadStatus.PENDING:
            history = self.run_database_load(history.id, artifact.artifact_bytes)
        return history

    def describe_blocked_period(self, current: UploadHistory) -> str:
        """Mensagem de envio recusado porque o mês já foi enviado e o contexto não aceita reenvio."""
        return (
            f"{describe_current_upload(current)}. Este contexto não aceita reenviar um mês; "
            "fale com o administrador."
        )

    def run_database_load(self, upload_id: int, parquet_bytes: bytes | None = None) -> UploadHistory:
        """Carrega (ou recarrega) o Parquet de um upload na tabela do contexto e registra o resultado.

        Falhas do banco (conexão, tabela incompatível, etc.) não são
        propagadas: viram `load_status=ERROR` com a mensagem em `load_error`,
        e o upload pode ser recarregado depois pelo Audit Log.

        Args:
            upload_id: Id do `UploadHistory` a carregar.
            parquet_bytes: Conteúdo do Parquet, quando já está em memória (logo
                após o upload). `None` lê de volta do MinIO/pasta local.

        Returns:
            O `UploadHistory` atualizado com a situação da carga.

        Raises:
            UploadNotFoundError: Se o upload não existir.
            LoadNotApplicableError: Se o upload não gerou um Parquet, se o
                contexto não existir mais ou estiver com a carga desligada.

        Um envio substituído por outro do mesmo mês não é carregado: fica com
        `load_status=SUPERSEDED`.
        """
        history = self._get_history(upload_id)
        if history.status != UploadStatus.SUCCESS or history.artifact_kind != "parquet":
            raise LoadNotApplicableError("Só envios com sucesso que geraram uma tabela podem ser carregados no banco.")
        context = self._context_service.get_by_name(history.context_name)
        if context is None:
            raise LoadNotApplicableError(f"O contexto '{history.context_name}' não existe mais.")
        if not context.load_to_database:
            raise LoadNotApplicableError(f"A carga no banco está desligada para o contexto '{context.name}'.")
        if history.superseded_by is not None:
            # Outro envio do mesmo mês já entrou no lugar deste: carregar agora o poria de volta.
            return self._update_load(upload_id, LoadStatus.SUPERSEDED)

        period = history.period if is_monthly(context) else None
        try:
            if self._database_loader is None:
                raise DatabaseNotConfiguredError("Carga no banco de dados não disponível nesta instalação.")
            data = parquet_bytes if parquet_bytes is not None else read_artifact_bytes(history)
            result = self._database_loader.load(data, context, history.id, period=period)
        except Exception as error:  # noqa: BLE001 - qualquer falha da carga fica registrada no audit log
            return self._update_load(upload_id, LoadStatus.ERROR, load_error=str(error))
        if result.skipped:
            return self._update_load(upload_id, LoadStatus.SUPERSEDED)
        return self._update_load(upload_id, LoadStatus.SUCCESS, load_detail=result.table)

    def _should_load(self, context: Context, artifact: IngestResult) -> bool:
        """Indica se o artefato deve ser carregado no banco: contexto com carga ligada e artefato Parquet."""
        return bool(context.load_to_database) and artifact.artifact_kind == "parquet"

    def _get_history(self, upload_id: int) -> UploadHistory:
        """Busca um `UploadHistory` pelo id, já desanexado da sessão.

        Raises:
            UploadNotFoundError: Se não existir um registro com esse id.
        """
        with self._session_factory.session() as db_session:
            history = db_session.get(UploadHistory, upload_id)
            if history is None:
                raise UploadNotFoundError(f"Upload '{upload_id}' não encontrado.")
            db_session.expunge(history)
            return history

    def _update_load(
        self,
        upload_id: int,
        load_status: LoadStatus,
        load_detail: str | None = None,
        load_error: str | None = None,
    ) -> UploadHistory:
        """Grava a situação da carga no banco em um `UploadHistory` existente.

        Args:
            upload_id: Id do registro.
            load_status: Nova situação da carga.
            load_detail: Tabela de destino, em caso de sucesso.
            load_error: Mensagem de erro, em caso de falha.

        Returns:
            O registro atualizado, já desanexado da sessão.
        """
        with self._session_factory.session() as db_session:
            history = db_session.get(UploadHistory, upload_id)
            history.load_status = load_status
            history.load_error = load_error
            if load_status == LoadStatus.SUCCESS:
                history.load_detail = load_detail
                history.loaded_at = datetime.now(timezone.utc)
            db_session.flush()
            db_session.refresh(history)
            db_session.expunge(history)
            return history

    def record_error(
        self, context: Context, filename: str, uploaded_by: str, error_message: str
    ) -> UploadHistory:
        """Registra no audit log uma tentativa de upload que falhou antes de gravar em qualquer destino.

        Usado quando a leitura/conversão do arquivo falha (ex.: extensão não
        suportada, PDF corrompido) ou quando o usuário cancela um upload após
        ver um aviso de colunas divergentes.

        Args:
            context: Contexto selecionado pelo usuário.
            filename: Nome original do arquivo.
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

    def list_recent(self, limit: int = 20, allowed_context_names: set[str] | None = None) -> list[UploadHistory]:
        """Lista os uploads mais recentes, para exibição na tela principal.

        Args:
            limit: Quantidade máxima de registros a retornar.
            allowed_context_names: Nomes de contexts que o usuário autenticado
                pode acessar. Se informado (usuários comuns), a listagem é
                restrita a uploads desses contexts. `None` (admins) lista de
                todos os contexts.

        Returns:
            Lista de `UploadHistory` ordenada do mais recente para o mais antigo.
        """
        query = select(UploadHistory)
        if allowed_context_names is not None:
            query = query.where(UploadHistory.context_name.in_(allowed_context_names))
        query = query.order_by(UploadHistory.created_at.desc()).limit(limit)
        with self._session_factory.session() as db_session:
            return list(db_session.execute(query).scalars().all())

    def list_filtered(
        self,
        context_name: str | None = None,
        status: UploadStatus | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 200,
        period: str | None = None,
    ) -> list[UploadHistory]:
        """Lista uploads filtrados por contexto, status e período, para a tela de audit log.

        Args:
            context_name: Filtra por nome de contexto, se informado.
            status: Filtra por status (sucesso/erro), se informado.
            start_date: Data inicial (inclusive) do período, se informado.
            end_date: Data final (inclusive) do período, se informado.
            limit: Quantidade máxima de registros a retornar.
            period: Filtra pelo mês de competência (`AAAA-MM`), se informado.

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
        if period:
            query = query.where(UploadHistory.period == period)
        query = query.order_by(UploadHistory.created_at.desc()).limit(limit)

        with self._session_factory.session() as db_session:
            return list(db_session.execute(query).scalars().all())

    def list_period_uploads(self, context_name: str, year: int) -> list[UploadHistory]:
        """Lista os envios com sucesso de um contexto cujo mês de competência cai no ano informado.

        Args:
            context_name: Nome do contexto.
            year: Ano das competências.

        Returns:
            Envios (vigentes e substituídos) ordenados do mais antigo para o mais novo.
        """
        query = (
            select(UploadHistory)
            .where(
                UploadHistory.context_name == context_name,
                UploadHistory.status == UploadStatus.SUCCESS,
                UploadHistory.period.like(f"{year:04d}-%"),
            )
            .order_by(UploadHistory.id)
        )
        with self._session_factory.session() as db_session:
            return list(db_session.execute(query).scalars().all())
