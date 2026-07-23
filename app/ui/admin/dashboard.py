"""Página inicial da área administrativa (`/admin`)."""

from nicegui import ui

from app.auth.guard import AuthGuard
from app.ui.theme import AppTheme


class AdminDashboardPage:
    """Renderiza o painel inicial da área administrativa, com atalhos para as demais telas."""

    ROUTE = "/admin"

    def __init__(self, auth_guard: AuthGuard) -> None:
        """Inicializa a página do dashboard administrativo.

        Args:
            auth_guard: Guard de autenticação usado para restringir o acesso a admins.
        """
        self._auth_guard = auth_guard

    def register(self) -> None:
        """Registra a rota `/admin` no NiceGUI."""

        @ui.page(self.ROUTE)
        def _page() -> None:
            if self._auth_guard.require_admin():
                self._render()

    def _render(self) -> None:
        """Constrói o layout do painel administrativo."""
        AppTheme().apply_page_styles()

        with ui.header().classes("items-center justify-between px-6 py-3"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("admin_panel_settings", size="1.4em", color="primary")
                ui.label("Área Administrativa").classes("text-lg font-semibold")
            with ui.row().classes("items-center gap-3"):
                ui.button(
                    "Voltar ao upload", icon="arrow_back", color=None, on_click=lambda: ui.navigate.to("/")
                ).props("flat dense")
                ui.button("Sair", icon="logout", color=None, on_click=self._auth_guard.logout).props("flat dense")
        ui.separator()

        with ui.column().classes("w-full items-center p-6"):
            with ui.column().classes("w-full max-w-4xl gap-4"):
                ui.label("O que você quer gerenciar?").classes("text-sm text-muted mb-1")
                with ui.grid(columns="repeat(auto-fit, minmax(230px, 1fr))").classes("w-full gap-4"):
                    cards = [
                        (
                            "Contexts",
                            "Mapeamento de contextos para buckets/tabelas de destino",
                            "hub",
                            "/admin/contexts",
                        ),
                        ("Usuários", "Cadastro de contas de acesso ao sistema", "group", "/admin/users"),
                        ("Audit Log", "Histórico completo de uploads processados", "history", "/admin/audit"),
                    ]
                    for title, description, icon, route in cards:
                        with (
                            ui.card()
                            .classes("w-full p-5 gap-1 rounded-2xl shadow-sm surface-card cursor-pointer hover-lift")
                            .on("click", lambda route=route: ui.navigate.to(route))
                        ):
                            with ui.row().classes("icon-badge mb-1"):
                                ui.icon(icon)
                            ui.label(title).classes("text-base font-semibold")
                            ui.label(description).classes("text-sm text-muted")
