"""Página principal de upload (`/`): envio de arquivos para o contexto de negócio selecionado."""

from nicegui import events, ui

from app.auth.guard import AuthGuard
from app.ingestion.file_types import FileTypeRegistry
from app.models.context import Context, DestinationType, WriteMode
from app.services.column_check import ColumnMismatch
from app.services.container import get_container
from app.ui.theme import AppTheme

_DESTINATION_ICONS = {
    DestinationType.MINIO: "cloud",
    DestinationType.SQLSERVER: "storage",
    DestinationType.LOCAL: "folder",
}

_STATUS_CHIP_SLOT = """
<q-td :props="props">
    <q-badge :color="props.row.status === 'success' ? 'positive' : 'negative'" rounded>
        {{ props.row.status === 'success' ? 'Sucesso' : 'Erro' }}
    </q-badge>
</q-td>
"""


class UploadPage:
    """Renderiza e controla a página principal de upload de arquivos."""

    ROUTE = "/"

    def __init__(self, auth_guard: AuthGuard) -> None:
        """Inicializa a página de upload.

        Args:
            auth_guard: Guard de autenticação usado para proteger a rota e
                identificar o usuário autenticado.
        """
        self._auth_guard = auth_guard

    def register(self) -> None:
        """Registra a rota `/` no NiceGUI."""

        @ui.page(self.ROUTE)
        def _page() -> None:
            if self._auth_guard.require_login():
                self._render()

    def _render(self) -> None:
        """Constrói o layout da página de upload."""
        AppTheme().apply_page_styles()
        container = get_container()
        current_user = container.user_service.get_by_id(self._auth_guard.current_user_id() or -1)
        if current_user is None:
            self._auth_guard.logout()
            return

        has_any_active_context = bool(container.context_service.list_active())
        contexts = container.user_context_service.list_accessible_contexts(current_user)
        contexts_by_name: dict[str, Context] = {context.name: context for context in contexts}
        file_type_registry = FileTypeRegistry()

        self._render_header()

        with ui.column().classes("w-full items-center gap-6 p-6"):
            with ui.column().classes("w-full sm:w-4/5 gap-6"):
                with ui.card().classes("w-full p-6 gap-1 rounded-2xl shadow-sm surface-card"):
                    with ui.row().classes("items-center gap-3 mb-1"):
                        with ui.row().classes("icon-badge"):
                            ui.icon("cloud_upload")
                        with ui.column().classes("gap-0"):
                            ui.label("Enviar arquivo").classes("text-lg font-semibold")
                            ui.label("Excel, CSV ou PDF — escolha o contexto de destino abaixo").classes(
                                "text-sm text-muted"
                            )

                    if not contexts_by_name:
                        with ui.row().classes("items-center gap-2 mt-3 text-muted"):
                            ui.icon("info", color="warning")
                            if has_any_active_context:
                                ui.label(
                                    "Você ainda não tem contexts liberados. Peça a um admin para liberar "
                                    "acesso em /admin/users."
                                )
                            else:
                                ui.label(
                                    "Nenhum contexto ativo. Peça a um admin para cadastrar um em /admin/contexts."
                                )
                    else:
                        default_context = (
                            current_user.last_context_name if current_user.last_context_name in contexts_by_name else None
                        )
                        context_select = (
                            ui.select(options=list(contexts_by_name.keys()), label="Contexto", value=default_context)
                            .props("outlined dense")
                            .classes("w-full mt-2")
                        )

                        with ui.row().classes("items-center gap-2 mt-2"):
                            destination_icon = ui.icon("help_outline", color="secondary")
                            destination_label = ui.label("Selecione um contexto").classes("text-sm text-muted")

                        write_mode_radio = ui.radio(
                            {
                                WriteMode.APPEND.value: "Append (adicionar à tabela existente)",
                                WriteMode.CREATE_NEW.value: "Criar nova tabela",
                            },
                        ).props("inline")
                        write_mode_radio.visible = False

                        def handle_context_change() -> None:
                            context = contexts_by_name.get(context_select.value)
                            if context is None:
                                destination_icon.set_name("help_outline")
                                destination_icon.set_text_color("secondary")
                                destination_label.set_text("Selecione um contexto")
                                write_mode_radio.visible = False
                                upload_widget.props('accept=".xlsx,.xls,.csv,.pdf"')
                                return
                            destination_icon.set_name(_DESTINATION_ICONS[context.destination_type])
                            destination_icon.set_text_color("primary")
                            if context.destination_type == DestinationType.MINIO:
                                destination_label.set_text(f'MinIO → bucket "{context.minio_bucket}"')
                                write_mode_radio.visible = False
                            elif context.destination_type == DestinationType.LOCAL:
                                destination_label.set_text(f"Pasta local → {context.local_path}")
                                write_mode_radio.visible = False
                            else:
                                destination_label.set_text(
                                    f"SQL Server → {context.db_schema_name}.{context.db_table}"
                                )
                                write_mode_radio.value = context.default_write_mode.value
                                write_mode_radio.visible = True

                            allowed_types = file_type_registry.deserialize(context.allowed_file_types)
                            allowed_extensions = file_type_registry.extensions_for_types(allowed_types)
                            upload_widget.props(f'accept="{",".join(allowed_extensions)}"')

                        context_select.on_value_change(lambda _: handle_context_change())

                        ui.separator().classes("my-3")

                        async def handle_upload(upload_event: events.UploadEventArguments) -> None:
                            selected = contexts_by_name.get(context_select.value)
                            if selected is None:
                                ui.notify("Selecione um contexto antes de enviar o arquivo.", type="warning")
                                upload_event.sender.reset()
                                return

                            # Recarrega o context do banco: a versão em memória (carregada quando a
                            # página abriu) pode estar desatualizada, por exemplo se um upload anterior
                            # nesta mesma sessão já mudou o `expected_columns` do context.
                            context = get_container().context_service.get_by_name(selected.name)
                            if context is None or not context.active:
                                ui.notify(f"Context '{selected.name}' não existe mais ou foi desativado.", type="negative")
                                upload_event.sender.reset()
                                return

                            write_mode = (
                                WriteMode(write_mode_radio.value)
                                if context.destination_type == DestinationType.SQLSERVER
                                else None
                            )
                            file_bytes = await upload_event.file.read()
                            filename = upload_event.file.name
                            username = self._auth_guard.current_username() or "desconhecido"
                            upload_service = get_container().upload_service

                            try:
                                artifact = upload_service.build_artifact(file_bytes, filename, context, username)
                            except Exception as error:  # noqa: BLE001 - erro de leitura vira registro de auditoria
                                upload_service.record_error(context, filename, write_mode, username, str(error))
                                ui.notify(f"Falha ao processar o arquivo: {error}", type="negative")
                                upload_event.sender.reset()
                                refresh_history_table()
                                return

                            mismatch = upload_service.check_column_mismatch(context, artifact)
                            if mismatch is not None and not await self._confirm_column_mismatch(mismatch):
                                upload_service.record_error(
                                    context,
                                    filename,
                                    write_mode,
                                    username,
                                    "Envio cancelado pelo usuário: colunas diferentes do último arquivo "
                                    "aceito para este contexto.",
                                )
                                ui.notify("Envio cancelado.", type="warning")
                                upload_event.sender.reset()
                                refresh_history_table()
                                return

                            history = upload_service.finalize(artifact, context, write_mode, filename, username)
                            if history.status.value == "success":
                                container.user_service.set_last_context(current_user.id, context.name)
                                ui.notify(
                                    f"Arquivo enviado com sucesso para {history.destination_detail}.",
                                    type="positive",
                                )
                            else:
                                ui.notify(f"Falha no envio: {history.error_message}", type="negative")

                            upload_event.sender.reset()
                            refresh_history_table()

                        upload_widget = ui.upload(
                            on_upload=handle_upload, auto_upload=False, max_file_size=200_000_000
                        ).props('accept=".xlsx,.xls,.csv,.pdf" color=primary flat bordered').classes(
                            "w-full rounded-xl"
                        )
                        handle_context_change()

                with ui.card().classes("w-full p-6 gap-1 rounded-2xl shadow-sm surface-card"):
                    with ui.row().classes("items-center gap-3 mb-2"):
                        with ui.row().classes("icon-badge"):
                            ui.icon("history")
                        ui.label("Últimos envios").classes("text-lg font-semibold")

                    history_table = ui.table(
                        columns=[
                            {"name": "filename", "label": "Arquivo", "field": "filename", "align": "left"},
                            {"name": "context_name", "label": "Contexto", "field": "context_name", "align": "left"},
                            {
                                "name": "destination_detail",
                                "label": "Destino",
                                "field": "destination_detail",
                                "align": "left",
                            },
                            {"name": "status", "label": "Status", "field": "status", "align": "center"},
                            {"name": "uploaded_by", "label": "Enviado por", "field": "uploaded_by", "align": "left"},
                            {"name": "created_at", "label": "Data de envio", "field": "created_at", "align": "left"},
                        ],
                        rows=[],
                        row_key="id",
                    ).props("flat bordered wrap-cells").classes("w-full")
                    history_table.add_slot("body-cell-status", _STATUS_CHIP_SLOT)

                    def refresh_history_table() -> None:
                        history_table.rows = [
                            {
                                "id": item.id,
                                "filename": item.filename,
                                "context_name": item.context_name,
                                "destination_detail": item.destination_detail or "-",
                                "status": item.status.value,
                                "uploaded_by": item.uploaded_by,
                                "created_at": item.created_at.strftime("%d/%m/%Y %H:%M"),
                            }
                            for item in get_container().upload_service.list_recent(limit=20)
                        ]

                    refresh_history_table()

    async def _confirm_column_mismatch(self, mismatch: ColumnMismatch) -> bool:
        """Mostra um diálogo pedindo confirmação quando as colunas do arquivo divergem das anteriores.

        Args:
            mismatch: Diferença detectada entre as colunas esperadas e as recebidas.

        Returns:
            `True` se o usuário confirmar o envio mesmo assim, `False` se cancelar.
        """
        with ui.dialog() as dialog, ui.card().classes("w-[28rem] p-6 gap-2 rounded-2xl"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("warning", color="warning", size="1.5em")
                ui.label("Colunas diferentes do último envio").classes("text-lg font-semibold")
            ui.label(
                "Este arquivo tem colunas diferentes das do último arquivo aceito para este contexto."
            ).classes("text-sm text-muted")
            if mismatch.extra_columns:
                ui.label(f"Novas: {', '.join(mismatch.extra_columns)}").classes("text-sm")
            if mismatch.missing_columns:
                ui.label(f"Faltando: {', '.join(mismatch.missing_columns)}").classes("text-sm")
            ui.label("Deseja enviar mesmo assim?").classes("text-sm mt-2")
            with ui.row().classes("w-full justify-end gap-2 mt-3"):
                ui.button("Cancelar", on_click=lambda: dialog.submit(False)).props("flat")
                ui.button("Enviar mesmo assim", on_click=lambda: dialog.submit(True)).props(
                    "unelevated color=warning"
                )

        return bool(await dialog)

    def _render_header(self) -> None:
        """Constrói o cabeçalho da página, com identificação do usuário e atalhos de navegação."""
        dark_mode = ui.dark_mode()
        with ui.header().classes("items-center justify-between px-6 py-3"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("cloud_upload", size="1.4em", color="primary")
                ui.label("Ingestão de Arquivos").classes("text-lg font-semibold")
            with ui.row().classes("items-center gap-3"):
                username = self._auth_guard.current_username()
                ui.label(f"Olá, {username}").classes("text-sm text-muted")
                if self._auth_guard.is_admin():
                    ui.button(
                        "Admin", icon="admin_panel_settings", color=None, on_click=lambda: ui.navigate.to("/admin")
                    ).props("flat dense")
                ui.button(icon="dark_mode", color=None, on_click=lambda: dark_mode.toggle()).props("flat dense round")
                ui.button("Sair", icon="logout", color=None, on_click=self._auth_guard.logout).props("flat dense")
        ui.separator()
