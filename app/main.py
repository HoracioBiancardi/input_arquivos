"""Ponto de entrada da aplicação: cria o FastAPI app, registra rotas da API e monta a UI NiceGUI."""

from fastapi import FastAPI
from nicegui import ui

from app.api.routes_audit import router as audit_router
from app.api.routes_contexts import router as contexts_router
from app.api.routes_upload import router as upload_router
from app.auth.guard import AuthGuard
from app.config import get_settings
from app.db.bootstrap import DatabaseBootstrapper
from app.db.session import get_session_factory
from app.services.container import get_container
from app.ui.admin.audit import AdminAuditPage
from app.ui.admin.contexts import AdminContextsPage
from app.ui.admin.dashboard import AdminDashboardPage
from app.ui.admin.users import AdminUsersPage
from app.ui.pages.login import LoginPage
from app.ui.pages.upload import UploadPage
from app.ui.theme import AppTheme


def create_app() -> FastAPI:
    """Cria e configura a aplicação FastAPI, incluindo a API REST e as páginas NiceGUI.

    Returns:
        Instância do FastAPI pronta para ser servida pelo Uvicorn.
    """
    settings = get_settings()

    fastapi_app = FastAPI(title="Sistema de Ingestão de Arquivos")
    fastapi_app.include_router(contexts_router)
    fastapi_app.include_router(upload_router)
    fastapi_app.include_router(audit_router)

    container = get_container()
    DatabaseBootstrapper(get_session_factory(), container.auth_service).run()

    AppTheme().configure_colors()

    auth_guard = AuthGuard()
    LoginPage(auth_guard).register()
    UploadPage(auth_guard).register()
    AdminDashboardPage(auth_guard).register()
    AdminContextsPage(auth_guard).register()
    AdminUsersPage(auth_guard).register()
    AdminAuditPage(auth_guard).register()

    ui.run_with(fastapi_app, title="Ingestão de Arquivos", storage_secret=settings.storage_secret)
    return fastapi_app


app = create_app()
