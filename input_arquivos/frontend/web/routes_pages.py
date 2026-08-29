"""Rotas de página: renderizam os templates Jinja2 servidos pelo FastAPI."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from input_arquivos.backend.auth.dependencies import require_admin_page, require_login_page
from input_arquivos.backend.auth.session import SessionUser

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory="input_arquivos/frontend/templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    """Renderiza a página de login.

    Args:
        request: Requisição HTTP recebida.

    Returns:
        Página de login renderizada.
    """
    return templates.TemplateResponse(request, "login.html", {"current_user": None})


@router.get("/", response_class=HTMLResponse, response_model=None)
def upload_page(
    request: Request, user: SessionUser | RedirectResponse = Depends(require_login_page)
) -> HTMLResponse | RedirectResponse:
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


@router.get("/uploads/{upload_id}/preview", response_class=HTMLResponse, response_model=None)
def upload_preview_page(
    request: Request, upload_id: int, user: SessionUser | RedirectResponse = Depends(require_login_page)
) -> HTMLResponse | RedirectResponse:
    """Renderiza a tela de visualização da tabela gerada por um upload.

    Args:
        request: Requisição HTTP recebida.
        upload_id: Identificador do upload a visualizar.
        user: Usuário autenticado, ou um redirect para `/login` se não houver sessão.

    Returns:
        Página de visualização renderizada, ou o redirect resolvido pela dependency.
    """
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(
        request, "upload_preview.html", {"current_user": user, "upload_id": upload_id}
    )


@router.get("/admin", response_class=HTMLResponse, response_model=None)
def admin_dashboard_page(
    request: Request, user: SessionUser | RedirectResponse = Depends(require_admin_page)
) -> HTMLResponse | RedirectResponse:
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


@router.get("/admin/contexts", response_class=HTMLResponse, response_model=None)
def admin_contexts_page(
    request: Request, user: SessionUser | RedirectResponse = Depends(require_admin_page)
) -> HTMLResponse | RedirectResponse:
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


@router.get("/admin/users", response_class=HTMLResponse, response_model=None)
def admin_users_page(
    request: Request, user: SessionUser | RedirectResponse = Depends(require_admin_page)
) -> HTMLResponse | RedirectResponse:
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


@router.get("/admin/settings", response_class=HTMLResponse, response_model=None)
def admin_settings_page(
    request: Request, user: SessionUser | RedirectResponse = Depends(require_admin_page)
) -> HTMLResponse | RedirectResponse:
    """Renderiza a página administrativa de configuração global do MinIO.

    Args:
        request: Requisição HTTP recebida.
        user: Usuário autenticado como admin, ou um redirect se não for o caso.

    Returns:
        Página de configurações renderizada, ou o redirect resolvido pela dependency.
    """
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse(request, "admin/settings.html", {"current_user": user})


@router.get("/admin/audit", response_class=HTMLResponse, response_model=None)
def admin_audit_page(
    request: Request, user: SessionUser | RedirectResponse = Depends(require_admin_page)
) -> HTMLResponse | RedirectResponse:
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
