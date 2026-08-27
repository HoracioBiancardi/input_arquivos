"""Dependencies do FastAPI para exigir login/admin nas rotas de API e de página."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from input_arquivos.backend.auth.session import SessionCookie, SessionUser
from input_arquivos.backend.models.user import UserRole

_session_cookie = SessionCookie()

LOGIN_PATH = "/login"
HOME_PATH = "/"


def _resolve_session_user(request: Request) -> SessionUser | None:
    """Lê o cookie de sessão e revalida seus dados contra o banco a cada requisição.

    O cookie assinado carrega `user_id`/`username`/`role` no momento do
    login, mas fica válido por até `session_max_age_seconds` (12h por
    padrão). Sem essa revalidação, um usuário desativado ou rebaixado de
    admin para user continuaria com o papel antigo "congelado" no cookie até
    ele expirar. Aqui a conta é buscada no banco a cada requisição e o `role`
    retornado é sempre o atual — nunca o que veio no cookie.

    Args:
        request: Requisição HTTP recebida.

    Returns:
        O usuário autenticado com os dados atuais do banco, ou `None` se o
        cookie for inválido/ausente, ou se a conta não existir mais, estiver
        inativa, ou o username não bater mais com o `user_id` do cookie.
    """
    from input_arquivos.backend.services.container import get_container

    session_user = _session_cookie.read(request)
    if session_user is None:
        return None

    db_user = get_container().user_service.get_by_id(session_user.user_id)
    if db_user is None or not db_user.active or db_user.username != session_user.username:
        return None

    return SessionUser(
        user_id=db_user.id,
        username=db_user.username,
        role=db_user.role.value,
        must_change_password=db_user.must_change_password,
    )


def get_optional_user(request: Request) -> SessionUser | None:
    """Lê o usuário da sessão atual, sem exigir que esteja autenticado.

    Args:
        request: Requisição HTTP recebida.

    Returns:
        O usuário autenticado (com dados revalidados contra o banco), ou
        `None` se não houver sessão válida.
    """
    return _resolve_session_user(request)


def require_login(user: SessionUser | None = Depends(get_optional_user)) -> SessionUser:
    """Exige um usuário autenticado; usado em rotas de API.

    Args:
        user: Usuário resolvido pela sessão atual.

    Returns:
        O usuário autenticado.

    Raises:
        HTTPException: 401 se não houver usuário autenticado.
    """
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login necessário.")
    return user


def require_admin(user: SessionUser = Depends(require_login)) -> SessionUser:
    """Exige um usuário autenticado com papel de admin; usado em rotas de API.

    Args:
        user: Usuário autenticado resolvido por `require_login`.

    Returns:
        O usuário autenticado, já validado como admin.

    Raises:
        HTTPException: 403 se o usuário autenticado não for admin.
    """
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso restrito a administradores.")
    return user


def require_login_page(request: Request) -> SessionUser | RedirectResponse:
    """Exige login numa rota de página, redirecionando para `/login` em vez de levantar 401.

    Args:
        request: Requisição HTTP recebida.

    Returns:
        O usuário autenticado, ou um `RedirectResponse` para `/login` que a
        rota deve retornar diretamente caso não haja sessão válida.
    """
    user = _resolve_session_user(request)
    if user is None:
        return RedirectResponse(LOGIN_PATH, status_code=status.HTTP_303_SEE_OTHER)
    return user


def require_admin_page(request: Request) -> SessionUser | RedirectResponse:
    """Exige admin numa rota de página, redirecionando conforme o caso.

    Args:
        request: Requisição HTTP recebida.

    Returns:
        O usuário autenticado (já validado como admin), ou um
        `RedirectResponse` que a rota deve retornar diretamente: para
        `/login` se não houver sessão, ou para `/` se o usuário não for admin.
    """
    user = _resolve_session_user(request)
    if user is None:
        return RedirectResponse(LOGIN_PATH, status_code=status.HTTP_303_SEE_OTHER)
    if user.role != UserRole.ADMIN.value:
        return RedirectResponse(HOME_PATH, status_code=status.HTTP_303_SEE_OTHER)
    return user
