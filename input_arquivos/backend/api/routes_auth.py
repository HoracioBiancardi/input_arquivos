"""Rotas da API REST de autenticação: login, logout, troca da própria senha e usuário da sessão atual."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from input_arquivos.backend.auth.dependencies import get_optional_user, require_login
from input_arquivos.backend.auth.session import SessionCookie, SessionUser
from input_arquivos.backend.schemas.auth import ChangePasswordRequest, LoginRequest, SessionUserResponse
from input_arquivos.backend.services.auth_service import AccountLockedError
from input_arquivos.backend.services.container import get_container
from input_arquivos.backend.services.user_service import InvalidCredentialsError, SamePasswordError

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
    _session_cookie.issue_for(response, user)
    return SessionUserResponse(username=user.username, role=user.role.value, must_change_password=user.must_change_password)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, user: SessionUser | None = Depends(get_optional_user)) -> None:
    """Encerra a sessão: apaga o cookie e invalida os cookies já emitidos para a conta.

    Só apagar o cookie no navegador não basta — uma cópia dele (roubada, ou em
    outro dispositivo) continuaria válida até expirar. Por isso a versão de
    sessão da conta é incrementada, o que encerra as sessões em todos os
    dispositivos.

    Args:
        response: Resposta HTTP de onde o cookie de sessão é removido.
        user: Usuário da sessão atual, se houver.
    """
    if user is not None:
        get_container().user_service.revoke_sessions(user.user_id)
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


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    response: Response,
    current: SessionUser | None = Depends(get_optional_user),
) -> None:
    """Troca a senha de quem informar usuário e senha atual (sem exigir sessão).

    Serve tanto à tela de login ("Trocar senha") quanto ao "Minha senha" do
    cabeçalho. Zera `must_change_password`. Todas as sessões já abertas da
    conta caem (a troca incrementa `session_version`), menos a de quem trocou
    a própria senha logado: essa recebe um cookie novo e continua.

    Args:
        payload: Usuário, senha atual e senha nova.
        response: Resposta HTTP, onde o cookie é reemitido para quem está logado.
        current: Usuário da sessão atual, se houver.

    Raises:
        HTTPException: 401 se usuário/senha atual forem inválidos ou a conta
            estiver bloqueada (mesmo status do login, para não permitir
            enumerar usernames); 422 se a senha nova for igual à atual.
    """
    try:
        get_container().user_service.change_own_password(
            payload.username, payload.current_password, payload.new_password
        )
    except AccountLockedError as error:
        minutes = max(1, error.retry_after_seconds // 60)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Conta bloqueada temporariamente por excesso de tentativas. Tente novamente em {minutes} minuto(s).",
        ) from error
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
    except SamePasswordError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"field": "new_password", "message": str(error)},
        ) from error
    if current is not None and current.username == payload.username:
        user = get_container().user_service.get_by_id(current.user_id)
        if user is not None:
            _session_cookie.issue_for(response, user)
