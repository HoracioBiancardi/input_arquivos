"""Página administrativa de CRUD de contexts (`/admin/contexts`)."""

from collections.abc import Callable

from nicegui import events, ui

from app.auth.guard import AuthGuard
from app.ingestion.file_types import FileType, FileTypeRegistry
from app.models.context import Context, DestinationType, PdfMode, WriteMode
from app.services.container import get_container
from app.ui.theme import AppTheme

_FILE_TYPE_LABELS = {FileType.EXCEL: "Excel", FileType.CSV: "CSV", FileType.PDF: "PDF"}

_PDF_MODE_HELP = {
    PdfMode.EXTRACT_TABLES: "Tenta extrair tabelas estruturadas do PDF (funciona melhor em PDFs com tabelas bem definidas).",
    PdfMode.METADATA_ONLY: "Gera uma linha com nome do arquivo, quantidade de páginas e o texto extraído, sem tentar estruturar tabelas.",
    PdfMode.RAW_ARCHIVE: "Não converte para Parquet: arquiva o PDF original diretamente no bucket MinIO ou na pasta local do contexto.",
}


class AdminContextsPage:
    """Renderiza e controla o CRUD de contexts na área administrativa."""

    ROUTE = "/admin/contexts"

    def __init__(self, auth_guard: AuthGuard) -> None:
        """Inicializa a página de contexts.

        Args:
            auth_guard: Guard de autenticação usado para restringir o acesso a admins.
        """
        self._auth_guard = auth_guard

    def register(self) -> None:
        """Registra a rota `/admin/contexts` no NiceGUI."""

        @ui.page(self.ROUTE)
        def _page() -> None:
            if self._auth_guard.require_admin():
                self._render()

    def _render(self) -> None:
        """Constrói o layout da página, incluindo a tabela de contexts e o diálogo de edição."""
        AppTheme().apply_page_styles()

        with ui.header().classes("items-center justify-between px-6 py-3"):
            ui.label("Contexts").classes("text-lg font-semibold")
            ui.button("Voltar", icon="arrow_back", color=None, on_click=lambda: ui.navigate.to("/admin")).props(
                "flat dense"
            )
        ui.separator()

        with ui.column().classes("w-full items-center p-6"):
            with ui.column().classes("w-full max-w-5xl gap-4"):
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label("Contexts cadastrados").classes("text-sm text-muted")
                    ui.button("Novo Context", icon="add", on_click=lambda: self._open_dialog(None)).props(
                        "unelevated"
                    )

                table = (
                    ui.table(
                        columns=[
                            {"name": "name", "label": "Nome", "field": "name", "align": "left"},
                            {"name": "destination", "label": "Destino", "field": "destination", "align": "left"},
                            {"name": "file_types", "label": "Tipos aceitos", "field": "file_types", "align": "left"},
                            {"name": "pdf_mode", "label": "Modo PDF", "field": "pdf_mode", "align": "left"},
                            {"name": "active", "label": "Ativo", "field": "active", "align": "center"},
                        ],
                        rows=[],
                        row_key="id",
                    )
                    .props("flat bordered wrap-cells")
                    .classes("w-full surface-card rounded-xl")
                )
                table.add_slot(
                    "body-cell-active",
                    """
                    <q-td :props="props">
                        <q-badge :color="props.row.active === 'Sim' ? 'positive' : 'grey'" rounded>{{ props.row.active }}</q-badge>
                    </q-td>
                    """,
                )

                def refresh_table() -> None:
                    registry = FileTypeRegistry()
                    contexts = get_container().context_service.list_all()
                    table.rows = [
                        {
                            "id": context.id,
                            "name": context.name,
                            "destination": self._describe_destination(context),
                            "file_types": ", ".join(
                                _FILE_TYPE_LABELS[ft] for ft in registry.deserialize(context.allowed_file_types)
                            ),
                            "pdf_mode": context.pdf_mode.value,
                            "active": "Sim" if context.active else "Não",
                        }
                        for context in contexts
                    ]

                def handle_row_click(event: events.GenericEventArguments) -> None:
                    context_id = event.args[1]["id"]
                    context = get_container().context_service.get_by_id(context_id)
                    if context is not None:
                        self._open_dialog(context, on_saved=refresh_table)

                table.on("rowClick", handle_row_click)
                refresh_table()

    def _describe_destination(self, context: Context) -> str:
        """Monta uma descrição curta do destino de um context, para exibição na tabela.

        Args:
            context: Context a descrever.

        Returns:
            Texto descrevendo o destino ("MinIO → bucket", "SQL Server →
            schema.tabela" ou "Local → pasta").
        """
        if context.destination_type == DestinationType.MINIO:
            return f"MinIO → {context.minio_bucket}"
        if context.destination_type == DestinationType.LOCAL:
            return f"Local → {context.local_path}"
        return f"SQL Server → {context.db_schema_name}.{context.db_table}"

    def _open_dialog(self, context: Context | None, on_saved: Callable[[], None] | None = None) -> None:
        """Abre o diálogo de criação/edição de um context.

        Args:
            context: Context a editar, ou `None` para criar um novo.
            on_saved: Callback executado após salvar com sucesso, tipicamente
                para atualizar a tabela da página.
        """
        is_edit = context is not None
        with ui.dialog() as dialog, ui.card().classes("w-[32rem] p-6 gap-2 rounded-2xl"):
            ui.label("Editar Context" if is_edit else "Novo Context").classes("text-xl font-semibold mb-1")

            name_input = ui.input("Nome do contexto", value=context.name if context else "").props(
                "outlined dense"
            ).classes("w-full")

            file_type_registry = FileTypeRegistry()
            allowed_types_select = ui.select(
                {file_type.value: label for file_type, label in _FILE_TYPE_LABELS.items()},
                label="Tipos de arquivo aceitos",
                multiple=True,
                value=[
                    file_type.value
                    for file_type in file_type_registry.deserialize(context.allowed_file_types if context else None)
                ],
            ).props("outlined dense use-chips").classes("w-full")

            destination_select = ui.select(
                {
                    DestinationType.MINIO.value: "MinIO",
                    DestinationType.SQLSERVER.value: "SQL Server",
                    DestinationType.LOCAL.value: "Pasta local",
                },
                label="Destino",
                value=(context.destination_type.value if context else DestinationType.MINIO.value),
            ).props("outlined dense").classes("w-full")

            with ui.column().classes("w-full gap-2") as minio_fields:
                bucket_input = ui.input("Bucket MinIO", value=context.minio_bucket if context else "").props(
                    "outlined dense"
                ).classes("w-full")
                minio_test_result = ui.label().classes("text-sm")

                def test_minio() -> None:
                    result = get_container().context_service.test_minio_connection(bucket_input.value or "")
                    minio_test_result.set_text(result.message)
                    minio_test_result.classes(
                        replace="text-sm " + ("text-green-600" if result.success else "text-red-600")
                    )

                ui.button("Testar conexão MinIO", on_click=test_minio).props("outline dense")

            with ui.column().classes("w-full gap-2") as db_fields:
                connection_input = ui.input(
                    "Connection string (SQLAlchemy)",
                    value=context.db_connection_string if context else "",
                ).props("outlined dense").classes("w-full")
                schema_input = ui.input(
                    "Schema", value=context.db_schema_name if context else "dbo"
                ).props("outlined dense").classes("w-full")
                table_input = ui.input("Tabela", value=context.db_table if context else "").props(
                    "outlined dense"
                ).classes("w-full")
                db_test_result = ui.label().classes("text-sm")

                def test_db() -> None:
                    result = get_container().context_service.test_db_connection(connection_input.value or "")
                    db_test_result.set_text(result.message)
                    db_test_result.classes(
                        replace="text-sm " + ("text-green-600" if result.success else "text-red-600")
                    )

                ui.button("Testar conexão do banco", on_click=test_db).props("outline dense")

            with ui.column().classes("w-full gap-2") as local_fields:
                local_path_input = ui.input(
                    "Pasta raiz local (opcional)",
                    value=context.local_path if context else "",
                ).props("outlined dense").classes("w-full")
                ui.label(
                    "Se deixar em branco, os arquivos são salvos a partir da raiz do projeto."
                ).classes("text-xs text-muted")
                local_test_result = ui.label().classes("text-sm")

                def test_local() -> None:
                    result = get_container().context_service.test_local_path(local_path_input.value or "")
                    local_test_result.set_text(result.message)
                    local_test_result.classes(
                        replace="text-sm " + ("text-green-600" if result.success else "text-red-600")
                    )

                ui.button("Testar/criar pasta local", on_click=test_local).props("outline dense")

            def toggle_destination_fields() -> None:
                selected = DestinationType(destination_select.value)
                minio_fields.visible = selected == DestinationType.MINIO
                db_fields.visible = selected == DestinationType.SQLSERVER
                local_fields.visible = selected == DestinationType.LOCAL

            destination_select.on_value_change(lambda _: toggle_destination_fields())
            toggle_destination_fields()

            write_mode_select = ui.select(
                {WriteMode.APPEND.value: "Append", WriteMode.CREATE_NEW.value: "Criar nova tabela"},
                label="Modo de escrita padrão",
                value=(context.default_write_mode.value if context else WriteMode.APPEND.value),
            ).props("outlined dense").classes("w-full")

            pdf_mode_select = ui.select(
                {mode.value: mode.value for mode in PdfMode},
                label="Modo de tratamento de PDF",
                value=(context.pdf_mode.value if context else PdfMode.METADATA_ONLY.value),
            ).props("outlined dense").classes("w-full")
            pdf_help_label = ui.label().classes("text-xs text-gray-500")

            def update_pdf_help() -> None:
                pdf_help_label.set_text(_PDF_MODE_HELP[PdfMode(pdf_mode_select.value)])

            pdf_mode_select.on_value_change(lambda _: update_pdf_help())
            update_pdf_help()

            active_switch = ui.switch("Ativo", value=context.active if context else True)

            def save() -> None:
                if not allowed_types_select.value:
                    ui.notify("Selecione ao menos um tipo de arquivo aceito.", type="warning")
                    return

                fields = {
                    "name": name_input.value,
                    "destination_type": DestinationType(destination_select.value),
                    "minio_bucket": bucket_input.value or None,
                    "db_connection_string": connection_input.value or None,
                    "db_schema_name": schema_input.value or "dbo",
                    "db_table": table_input.value or None,
                    "local_path": local_path_input.value or None,
                    "default_write_mode": WriteMode(write_mode_select.value),
                    "pdf_mode": PdfMode(pdf_mode_select.value),
                    "allowed_file_types": file_type_registry.serialize(
                        [FileType(value) for value in allowed_types_select.value]
                    ),
                    "active": active_switch.value,
                }
                if is_edit:
                    get_container().context_service.update(context.id, **fields)
                else:
                    get_container().context_service.create(
                        name=fields["name"],
                        destination_type=fields["destination_type"],
                        default_write_mode=fields["default_write_mode"],
                        pdf_mode=fields["pdf_mode"],
                        minio_bucket=fields["minio_bucket"],
                        db_connection_string=fields["db_connection_string"],
                        db_schema_name=fields["db_schema_name"],
                        db_table=fields["db_table"],
                        local_path=fields["local_path"],
                        allowed_file_types=fields["allowed_file_types"],
                    )
                dialog.close()
                if on_saved:
                    on_saved()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Salvar", on_click=save).props("unelevated")

        dialog.open()
