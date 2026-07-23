"""Guard de autenticação para páginas NiceGUI, baseado em `app.storage.user`."""

from nicegui import app, ui

from app.models.user import UserRole


class AuthGuard:
    """Protege páginas NiceGUI exigindo login (e, opcionalmente, papel de admin).

    Usa a sessão nativa do NiceGUI (`app.storage.user`, cookie assinado por
    `storage_secret`) em vez de JWT: a UI é inteiramente NiceGUI, então um
    cookie de sessão assinado é suficiente e mais simples de manter.
    """

    LOGIN_PATH = "/login"
    HOME_PATH = "/"

    def is_authenticated(self) -> bool:
        """Verifica se há um usuário autenticado na sessão atual.

        Returns:
            `True` se houver um usuário autenticado nesta sessão.
        """
        return bool(app.storage.user.get("authenticated", False))

    def current_username(self) -> str | None:
        """Retorna o nome do usuário autenticado na sessão atual.

        Returns:
            Nome de usuário, ou `None` se ninguém estiver autenticado.
        """
        return app.storage.user.get("username")

    def current_role(self) -> str | None:
        """Retorna o papel (role) do usuário autenticado na sessão atual.

        Returns:
            Papel do usuário ("admin" ou "user"), ou `None` se ninguém estiver autenticado.
        """
        return app.storage.user.get("role")

    def current_user_id(self) -> int | None:
        """Retorna o identificador do usuário autenticado na sessão atual.

        Returns:
            Id do usuário, ou `None` se ninguém estiver autenticado.
        """
        return app.storage.user.get("user_id")

    def is_admin(self) -> bool:
        """Verifica se o usuário autenticado na sessão atual tem papel de admin.

        Returns:
            `True` se o usuário estiver autenticado e for admin.
        """
        return self.is_authenticated() and self.current_role() == UserRole.ADMIN.value

    def require_login(self) -> bool:
        """Garante que a página atual só continue renderizando se houver login.

        Redireciona para a tela de login caso não haja usuário autenticado.

        Returns:
            `True` se o usuário estiver autenticado (a página deve continuar
            renderizando); `False` caso o redirecionamento já tenha sido feito.
        """
        if not self.is_authenticated():
            ui.navigate.to(self.LOGIN_PATH)
            return False
        return True

    def require_admin(self) -> bool:
        """Garante que a página atual só continue renderizando para usuários admin.

        Redireciona para a tela de login se não houver usuário autenticado, ou
        para a página inicial se o usuário autenticado não for admin.

        Returns:
            `True` se o usuário estiver autenticado e for admin; `False` caso
            o redirecionamento já tenha sido feito.
        """
        if not self.require_login():
            return False
        if not self.is_admin():
            ui.navigate.to(self.HOME_PATH)
            return False
        return True

    def login(self, user_id: int, username: str, role: str) -> None:
        """Marca a sessão atual como autenticada.

        Args:
            user_id: Identificador do usuário autenticado.
            username: Nome do usuário autenticado.
            role: Papel do usuário autenticado ("admin" ou "user").
        """
        app.storage.user["authenticated"] = True
        app.storage.user["user_id"] = user_id
        app.storage.user["username"] = username
        app.storage.user["role"] = role

    def logout(self) -> None:
        """Encerra a sessão atual e redireciona para a tela de login."""
        app.storage.user.clear()
        ui.navigate.to(self.LOGIN_PATH)
