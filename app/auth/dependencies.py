"""Dependencies do FastAPI para exigir login/admin nas rotas de API e de página."""

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.auth.session import SessionCookie, SessionUser
from app.models.user import UserRole

_session_cookie = SessionCookie()

LOGIN_PATH = "/login"
HOME_PATH = "/"


def get_optional_user(request: Request) -> SessionUser | None:
    """Lê o usuário da sessão atual, sem exigir que esteja autenticado.

    Args:
        request: Requisição HTTP recebida.

    Returns:
        O usuário autenticado, ou `None` se não houver sessão válida.
    """
    return _session_cookie.read(request)


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
    user = _session_cookie.read(request)
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
    user = _session_cookie.read(request)
    if user is None:
        return RedirectResponse(LOGIN_PATH, status_code=status.HTTP_303_SEE_OTHER)
    if user.role != UserRole.ADMIN.value:
        return RedirectResponse(HOME_PATH, status_code=status.HTTP_303_SEE_OTHER)
    return user
