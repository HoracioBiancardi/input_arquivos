"""Rotas de página: renderizam os templates Jinja2 servidos pelo FastAPI."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.auth.dependencies import require_admin_page, require_login_page
from app.auth.session import SessionUser

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    """Renderiza a página de login.

    Args:
        request: Requisição HTTP recebida.

    Returns:
        Página de login renderizada.
    """
    return templates.TemplateResponse(request, "login.html", {"current_user": None})


@router.get("/", response_class=HTMLResponse)
def upload_page(request: Request, user: SessionUser | RedirectResponse = Depends(require_login_page)):
    """Renderiza a página principal de upload.

    Args:
        request: Requisição HTTP recebida.
        user: Usuário autenticado, ou um redirect para `/login` se não houver sessão.

    Returns:
        Página de upload renderizada, ou o redirect resolvido pela dependency.
    """
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(request, "upload.html", {"current_user": user})


@router.get("/admin", response_class=HTMLResponse)
def admin_dashboard_page(request: Request, user: SessionUser | RedirectResponse = Depends(require_admin_page)):
    """Renderiza o painel inicial da área administrativa.

    Args:
        request: Requisição HTTP recebida.
        user: Usuário autenticado como admin, ou um redirect se não for o caso.

    Returns:
        Página do painel administrativo renderizada, ou o redirect resolvido pela dependency.
    """
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(request, "admin/dashboard.html", {"current_user": user})


@router.get("/admin/contexts", response_class=HTMLResponse)
def admin_contexts_page(request: Request, user: SessionUser | RedirectResponse = Depends(require_admin_page)):
    """Renderiza a página administrativa de CRUD de contexts.

    Args:
        request: Requisição HTTP recebida.
        user: Usuário autenticado como admin, ou um redirect se não for o caso.

    Returns:
        Página de contexts renderizada, ou o redirect resolvido pela dependency.
    """
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(request, "admin/contexts.html", {"current_user": user})


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, user: SessionUser | RedirectResponse = Depends(require_admin_page)):
    """Renderiza a página administrativa de CRUD de usuários.

    Args:
        request: Requisição HTTP recebida.
        user: Usuário autenticado como admin, ou um redirect se não for o caso.

    Returns:
        Página de usuários renderizada, ou o redirect resolvido pela dependency.
    """
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(request, "admin/users.html", {"current_user": user})


@router.get("/admin/audit", response_class=HTMLResponse)
def admin_audit_page(request: Request, user: SessionUser | RedirectResponse = Depends(require_admin_page)):
    """Renderiza a página administrativa de audit log.

    Args:
        request: Requisição HTTP recebida.
        user: Usuário autenticado como admin, ou um redirect se não for o caso.

    Returns:
        Página de audit log renderizada, ou o redirect resolvido pela dependency.
    """
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(request, "admin/audit.html", {"current_user": user})
