"""Página administrativa de CRUD de usuários (`/admin/users`)."""

from collections.abc import Callable

from nicegui import events, ui

from app.auth.guard import AuthGuard
from app.models.user import UserRole
from app.services.container import get_container
from app.ui.theme import AppTheme


class AdminUsersPage:
    """Renderiza e controla o CRUD de usuários na área administrativa."""

    ROUTE = "/admin/users"

    def __init__(self, auth_guard: AuthGuard) -> None:
        """Inicializa a página de usuários.

        Args:
            auth_guard: Guard de autenticação usado para restringir o acesso a admins.
        """
        self._auth_guard = auth_guard

    def register(self) -> None:
        """Registra a rota `/admin/users` no NiceGUI."""

        @ui.page(self.ROUTE)
        def _page() -> None:
            if self._auth_guard.require_admin():
                self._render()

    def _render(self) -> None:
        """Constrói o layout da página, incluindo a tabela de usuários e o diálogo de criação."""
        AppTheme().apply_page_styles()

        with ui.header().classes("items-center justify-between px-6 py-3"):
            ui.label("Usuários").classes("text-lg font-semibold")
            ui.button("Voltar", icon="arrow_back", color=None, on_click=lambda: ui.navigate.to("/admin")).props(
                "flat dense"
            )
        ui.separator()

        with ui.column().classes("w-full items-center p-6"):
            with ui.column().classes("w-full max-w-4xl gap-4"):
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label("Usuários cadastrados").classes("text-sm text-muted")
                    ui.button(
                        "Novo Usuário", icon="add", on_click=lambda: self._open_create_dialog(refresh_table)
                    ).props("unelevated")

                table = (
                    ui.table(
                        columns=[
                            {"name": "username", "label": "Usuário", "field": "username", "align": "left"},
                            {"name": "role", "label": "Papel", "field": "role", "align": "left"},
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
                    users = get_container().user_service.list_all()
                    table.rows = [
                        {
                            "id": user.id,
                            "username": user.username,
                            "role": user.role.value,
                            "active": "Sim" if user.active else "Não",
                        }
                        for user in users
                    ]

                def handle_row_click(event: events.GenericEventArguments) -> None:
                    user_id = event.args[1]["id"]
                    self._open_manage_dialog(user_id, refresh_table)

                table.on("rowClick", handle_row_click)
                refresh_table()

    def _open_create_dialog(self, on_saved: Callable[[], None]) -> None:
        """Abre o diálogo de criação de um novo usuário.

        Args:
            on_saved: Callback executado após a criação, para atualizar a tabela.
        """
        with ui.dialog() as dialog, ui.card().classes("w-96 p-6 gap-2 rounded-2xl"):
            ui.label("Novo Usuário").classes("text-xl font-semibold mb-1")
            username_input = ui.input("Usuário").props("outlined dense").classes("w-full")
            password_input = ui.input("Senha", password=True, password_toggle_button=True).props(
                "outlined dense"
            ).classes("w-full")
            role_select = ui.select(
                {UserRole.USER.value: "Usuário comum", UserRole.ADMIN.value: "Admin"},
                label="Papel",
                value=UserRole.USER.value,
            ).props("outlined dense").classes("w-full")

            def save() -> None:
                if not username_input.value or not password_input.value:
                    ui.notify("Usuário e senha são obrigatórios.", type="warning")
                    return
                get_container().user_service.create(
                    username=username_input.value,
                    plain_password=password_input.value,
                    role=UserRole(role_select.value),
                )
                dialog.close()
                on_saved()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Criar", on_click=save).props("unelevated")

        dialog.open()

    def _open_manage_dialog(self, user_id: int, on_saved: Callable[[], None]) -> None:
        """Abre o diálogo de gerenciamento de um usuário existente (papel, ativação, reset de senha).

        Args:
            user_id: Identificador do usuário a gerenciar.
            on_saved: Callback executado após qualquer alteração, para atualizar a tabela.
        """
        users_by_id = {user.id: user for user in get_container().user_service.list_all()}
        user = users_by_id.get(user_id)
        if user is None:
            return

        with ui.dialog() as dialog, ui.card().classes("w-[28rem] p-6 gap-2 rounded-2xl"):
            ui.label(f"Gerenciar {user.username}").classes("text-xl font-semibold mb-1")

            role_select = ui.select(
                {UserRole.USER.value: "Usuário comum", UserRole.ADMIN.value: "Admin"},
                label="Papel",
                value=user.role.value,
            ).props("outlined dense").classes("w-full")
            active_switch = ui.switch("Ativo", value=user.active)

            new_password_input = ui.input("Nova senha (deixe em branco para não alterar)", password=True).props(
                "outlined dense"
            ).classes("w-full")

            active_contexts = get_container().context_service.list_active()
            assigned_ids = get_container().user_context_service.list_context_ids_for_user(user_id)
            with ui.column().classes("w-full gap-1") as contexts_field:
                contexts_select = ui.select(
                    {context.id: context.name for context in active_contexts},
                    label="Contexts permitidos",
                    multiple=True,
                    value=assigned_ids,
                ).props("outlined dense use-chips").classes("w-full")
                ui.label("Só se aplica a usuários comuns — admins acessam todos os contexts.").classes(
                    "text-xs text-muted"
                )

            def toggle_contexts_field() -> None:
                contexts_field.visible = role_select.value == UserRole.USER.value

            role_select.on_value_change(lambda _: toggle_contexts_field())
            toggle_contexts_field()

            def save() -> None:
                get_container().user_service.set_role(user_id, UserRole(role_select.value))
                get_container().user_service.set_active(user_id, active_switch.value)
                if new_password_input.value:
                    get_container().user_service.reset_password(user_id, new_password_input.value)
                get_container().user_context_service.set_contexts_for_user(user_id, list(contexts_select.value or []))
                dialog.close()
                on_saved()

            with ui.row().classes("w-full justify-end gap-2 mt-4"):
                ui.button("Cancelar", on_click=dialog.close).props("flat")
                ui.button("Salvar", on_click=save).props("unelevated")

        dialog.open()
