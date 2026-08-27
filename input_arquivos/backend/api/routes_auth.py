"""Rotas da API REST de autenticação: login, logout e usuário da sessão atual."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from input_arquivos.backend.auth.dependencies import require_login
from input_arquivos.backend.auth.session import SessionCookie, SessionUser
from input_arquivos.backend.schemas.auth import LoginRequest, SessionUserResponse
from input_arquivos.backend.services.auth_service import AccountLockedError
from input_arquivos.backend.services.container import get_container

router = APIRouter(prefix="/api/auth", tags=["auth"])
_session_cookie = SessionCookie()


@router.post("/login", response_model=SessionUserResponse)
def login(payload: LoginRequest, response: Response) -> SessionUserResponse:
    """Autentica o usuário e, em caso de sucesso, emite o cookie de sessão.

    Args:
        payload: Usuário e senha informados no formulário de login.
        response: Resposta HTTP onde o cookie de sessão é definido.

    Returns:
        Dados básicos do usuário autenticado.

    Raises:
        HTTPException: 401 se usuário/senha forem inválidos, ou se a conta
            estiver temporariamente bloqueada por tentativas erradas — mesmo
            status nos dois casos (a mensagem ainda diferencia, mas usar
            status codes diferentes permitiria enumerar usernames válidos só
            observando qual devolve 423 depois de várias tentativas).
    """
    try:
        user = get_container().auth_service.authenticate(payload.username, payload.password)
    except AccountLockedError as error:
        minutes = max(1, error.retry_after_seconds // 60)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Conta bloqueada temporariamente por excesso de tentativas. Tente novamente em {minutes} minuto(s).",
        ) from error
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Usuário ou senha inválidos.")
    _session_cookie.issue(response, SessionUser(user_id=user.id, username=user.username, role=user.role.value))
    return SessionUserResponse(username=user.username, role=user.role.value, must_change_password=user.must_change_password)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    """Encerra a sessão atual, removendo o cookie de sessão.

    Args:
        response: Resposta HTTP de onde o cookie de sessão é removido.
    """
    _session_cookie.clear(response)


@router.get("/me", response_model=SessionUserResponse)
def me(user: SessionUser = Depends(require_login)) -> SessionUserResponse:
    """Retorna os dados do usuário autenticado na sessão atual.

    Args:
        user: Usuário autenticado, resolvido a partir do cookie de sessão.

    Returns:
        Dados básicos do usuário autenticado.
    """
    return SessionUserResponse(username=user.username, role=user.role, must_change_password=user.must_change_password)
