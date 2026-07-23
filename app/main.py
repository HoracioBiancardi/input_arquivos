"""Ponto de entrada da aplicação: cria o FastAPI app e registra as rotas da API e das páginas."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from app.api.routes_audit import router as audit_router
from app.api.routes_auth import router as auth_router
from app.api.routes_contexts import router as contexts_router
from app.api.routes_upload import router as upload_router
from app.api.routes_users import router as users_router
from app.db.bootstrap import DatabaseBootstrapper
from app.db.session import get_session_factory
from app.services.container import get_container
from app.web.routes_pages import router as pages_router


def create_app() -> FastAPI:
    """Cria e configura a aplicação FastAPI, incluindo a API REST e as páginas HTML.

    Returns:
        Instância do FastAPI pronta para ser servida pelo Uvicorn.
    """
    fastapi_app = FastAPI(title="Sistema de Ingestão de Arquivos")
    fastapi_app.mount("/static", StaticFiles(directory="app/static"), name="static")

    @fastapi_app.exception_handler(IntegrityError)
    def _handle_integrity_error(_request: Request, _error: IntegrityError) -> JSONResponse:
        """Converte violações de constraint do banco (ex.: nome duplicado) numa resposta amigável.

        Rede de segurança para o caso raro de duas requisições concorrentes
        passarem pela checagem de duplicidade da camada de serviço ao mesmo
        tempo — o banco ainda impede a duplicidade via `unique=True`.
        """
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "Já existe um registro com esses dados."},
        )

    fastapi_app.include_router(auth_router)
    fastapi_app.include_router(contexts_router)
    fastapi_app.include_router(upload_router)
    fastapi_app.include_router(users_router)
    fastapi_app.include_router(audit_router)
    fastapi_app.include_router(pages_router)

    container = get_container()
    DatabaseBootstrapper(get_session_factory(), container.auth_service).run()

    return fastapi_app


app = create_app()
