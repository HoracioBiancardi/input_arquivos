"""Página administrativa de audit log de uploads (`/admin/audit`)."""

from datetime import datetime

from nicegui import ui

from app.auth.guard import AuthGuard
from app.models.upload_history import UploadStatus
from app.services.container import get_container
from app.ui.theme import AppTheme


class AdminAuditPage:
    """Renderiza e controla a tela de audit log, com filtros por contexto, status e período."""

    ROUTE = "/admin/audit"

    def __init__(self, auth_guard: AuthGuard) -> None:
        """Inicializa a página de audit log.

        Args:
            auth_guard: Guard de autenticação usado para restringir o acesso a admins.
        """
        self._auth_guard = auth_guard

    def register(self) -> None:
        """Registra a rota `/admin/audit` no NiceGUI."""

        @ui.page(self.ROUTE)
        def _page() -> None:
            if self._auth_guard.require_admin():
                self._render()

    def _render(self) -> None:
        """Constrói o layout da página, incluindo os filtros e a tabela de audit log."""
        AppTheme().apply_page_styles()

        with ui.header().classes("items-center justify-between px-6 py-3"):
            ui.label("Audit Log").classes("text-lg font-semibold")
            ui.button("Voltar", icon="arrow_back", color=None, on_click=lambda: ui.navigate.to("/admin")).props(
                "flat dense"
            )
        ui.separator()

        with ui.column().classes("w-full items-center p-6"):
            with ui.column().classes("w-full max-w-6xl gap-4"):
                context_names = [context.name for context in get_container().context_service.list_all()]

                with ui.card().classes("w-full p-4 gap-3 rounded-2xl shadow-sm surface-card"):
                    with ui.row().classes("w-full gap-3 items-end"):
                        context_filter = ui.select(
                            ["Todos", *context_names], label="Contexto", value="Todos"
                        ).props("outlined dense").classes("w-48")
                        status_filter = ui.select(
                            {
                                "Todos": "Todos",
                                UploadStatus.SUCCESS.value: "Sucesso",
                                UploadStatus.ERROR.value: "Erro",
                            },
                            label="Status",
                            value="Todos",
                        ).props("outlined dense").classes("w-40")
                        start_date_input = ui.input("Data inicial").props("outlined dense type=date")
                        end_date_input = ui.input("Data final").props("outlined dense type=date")
                        ui.button("Filtrar", icon="filter_alt", on_click=lambda: apply_filters()).props(
                            "unelevated"
                        )

                table = (
                    ui.table(
                        columns=[
                            {"name": "filename", "label": "Arquivo", "field": "filename", "align": "left"},
                            {"name": "context_name", "label": "Contexto", "field": "context_name", "align": "left"},
                            {
                                "name": "destination_detail",
                                "label": "Destino",
                                "field": "destination_detail",
                                "align": "left",
                            },
                            {"name": "write_mode", "label": "Modo", "field": "write_mode", "align": "left"},
                            {"name": "status", "label": "Status", "field": "status", "align": "center"},
                            {"name": "row_count", "label": "Linhas", "field": "row_count", "align": "right"},
                            {"name": "uploaded_by", "label": "Enviado por", "field": "uploaded_by", "align": "left"},
                            {"name": "created_at", "label": "Data de envio", "field": "created_at", "align": "left"},
                            {"name": "error_message", "label": "Erro", "field": "error_message", "align": "left"},
                        ],
                        rows=[],
                        row_key="id",
                    )
                    .props("flat bordered wrap-cells")
                    .classes("w-full surface-card rounded-xl")
                )
                table.add_slot(
                    "body-cell-status",
                    """
                    <q-td :props="props">
                        <q-badge :color="props.row.status === 'success' ? 'positive' : 'negative'" rounded>
                            {{ props.row.status === 'success' ? 'Sucesso' : 'Erro' }}
                        </q-badge>
                    </q-td>
                    """,
                )

                def apply_filters() -> None:
                    context_name = None if context_filter.value == "Todos" else context_filter.value
                    status = None if status_filter.value == "Todos" else UploadStatus(status_filter.value)
                    start_date = (
                        datetime.strptime(start_date_input.value, "%Y-%m-%d").date()
                        if start_date_input.value
                        else None
                    )
                    end_date = (
                        datetime.strptime(end_date_input.value, "%Y-%m-%d").date() if end_date_input.value else None
                    )
                    history = get_container().upload_service.list_filtered(
                        context_name=context_name, status=status, start_date=start_date, end_date=end_date
                    )
                    table.rows = [
                        {
                            "id": item.id,
                            "filename": item.filename,
                            "context_name": item.context_name,
                            "destination_detail": item.destination_detail or "-",
                            "write_mode": item.write_mode.value if item.write_mode else "-",
                            "status": item.status.value,
                            "row_count": item.row_count if item.row_count is not None else "-",
                            "uploaded_by": item.uploaded_by,
                            "created_at": item.created_at.strftime("%d/%m/%Y %H:%M"),
                            "error_message": item.error_message or "-",
                        }
                        for item in history
                    ]

                apply_filters()
