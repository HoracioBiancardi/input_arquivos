"""Página de login (`/login`), ponto de entrada único para usuários comuns e admins."""

from nicegui import ui

from app.auth.guard import AuthGuard
from app.services.container import get_container
from app.ui.theme import AppTheme

_BACKGROUND_STYLE = """
<style>
  .login-page {
    min-height: 100vh;
    background: radial-gradient(circle at 20% 20%, #eef2ff 0%, #f8fafc 45%, #f1f5f9 100%);
  }
  body.body--dark .login-page {
    background: radial-gradient(circle at 20% 20%, #1e1b4b 0%, #0f172a 45%, #0f172a 100%);
  }
</style>
"""


class LoginPage:
    """Renderiza e controla a página de login do sistema."""

    ROUTE = "/login"

    def __init__(self, auth_guard: AuthGuard) -> None:
        """Inicializa a página de login.

        Args:
            auth_guard: Guard de autenticação usado para marcar a sessão como autenticada.
        """
        self._auth_guard = auth_guard

    def register(self) -> None:
        """Registra a rota `/login` no NiceGUI."""

        @ui.page(self.ROUTE)
        def _page() -> None:
            self._render()

    def _render(self) -> None:
        """Constrói o layout da página de login."""
        AppTheme().apply_page_styles()
        ui.add_head_html(_BACKGROUND_STYLE)

        with ui.column().classes("login-page w-full items-center justify-center gap-4 p-4"):
            with ui.card().classes("w-full max-w-sm p-8 gap-1 rounded-2xl shadow-lg surface-card"):
                with ui.row().classes("icon-badge self-center mb-1"):
                    ui.icon("cloud_upload", size="1.5em")
                ui.label("Ingestão de Arquivos").classes("text-xl font-bold self-center text-center")
                ui.label("Entre com sua conta para continuar").classes(
                    "text-sm text-muted self-center text-center mb-3"
                )

                username_input = (
                    ui.input("Usuário")
                    .props('outlined dense prepend-icon="person"')
                    .classes("w-full")
                )
                password_input = (
                    ui.input("Senha", password=True, password_toggle_button=True)
                    .props('outlined dense prepend-icon="lock"')
                    .classes("w-full mt-1")
                )
                error_label = ui.label().classes("text-sm mt-1 text-red-600")

                def handle_login() -> None:
                    auth_service = get_container().auth_service
                    user = auth_service.authenticate(username_input.value or "", password_input.value or "")
                    if user is None:
                        error_label.set_text("Usuário ou senha inválidos.")
                        return
                    self._auth_guard.login(user_id=user.id, username=user.username, role=user.role.value)
                    ui.navigate.to("/")

                username_input.on("keydown.enter", lambda: handle_login())
                password_input.on("keydown.enter", lambda: handle_login())

                ui.button("Entrar", on_click=handle_login).props("unelevated").classes(
                    "w-full mt-3 py-1"
                )

            ui.label("Sistema de ingestão de arquivos • Excel, CSV e PDF").classes(
                "text-xs text-muted"
            )
