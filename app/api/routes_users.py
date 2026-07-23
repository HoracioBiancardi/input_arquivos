"""Rotas da API REST para CRUD de usuários e atribuição de acesso a contexts."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth.dependencies import require_admin
from app.schemas.user import (
    UserContextsRequest,
    UserCreateRequest,
    UserDetailResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.services.container import get_container
from app.services.user_service import DuplicateUsernameError

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[UserResponse])
def list_users() -> list[UserResponse]:
    """Lista todos os usuários cadastrados.

    Returns:
        Lista de usuários convertida para `UserResponse`.
    """
    users = get_container().user_service.list_all()
    return [UserResponse.model_validate(user) for user in users]


@router.post("", response_model=UserResponse)
def create_user(payload: UserCreateRequest) -> UserResponse:
    """Cria um novo usuário.

    Args:
        payload: Dados do usuário a ser criado.

    Returns:
        O usuário recém-criado, convertido para `UserResponse`.

    Raises:
        HTTPException: 409 se já existir um usuário com esse nome.
    """
    try:
        user = get_container().user_service.create(
            username=payload.username, plain_password=payload.password, role=payload.role
        )
    except DuplicateUsernameError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"field": "username", "message": str(error)}
        ) from error
    return UserResponse.model_validate(user)


@router.get("/{user_id}", response_model=UserDetailResponse)
def get_user(user_id: int) -> UserDetailResponse:
    """Busca um usuário pelo identificador, incluindo os contexts liberados para ele.

    Args:
        user_id: Identificador do usuário.

    Returns:
        O usuário encontrado, com a lista de ids de contexts liberados.

    Raises:
        HTTPException: 404 se o usuário não existir.
    """
    container = get_container()
    user = container.user_service.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    context_ids = container.user_context_service.list_context_ids_for_user(user_id)
    return UserDetailResponse(**UserResponse.model_validate(user).model_dump(), context_ids=context_ids)


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, payload: UserUpdateRequest) -> UserResponse:
    """Atualiza papel, ativação e/ou senha de um usuário existente.

    Args:
        user_id: Identificador do usuário a atualizar.
        payload: Campos a alterar (apenas os informados são aplicados).

    Returns:
        O usuário atualizado, convertido para `UserResponse`.

    Raises:
        HTTPException: 404 se o usuário não existir.
    """
    container = get_container()
    if container.user_service.get_by_id(user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")

    if payload.role is not None:
        container.user_service.set_role(user_id, payload.role)
    if payload.active is not None:
        container.user_service.set_active(user_id, payload.active)
    if payload.new_password:
        container.user_service.reset_password(user_id, payload.new_password)

    return UserResponse.model_validate(container.user_service.get_by_id(user_id))


@router.put("/{user_id}/contexts", status_code=status.HTTP_204_NO_CONTENT)
def set_user_contexts(user_id: int, payload: UserContextsRequest) -> None:
    """Substitui a lista de contexts liberados para um usuário.

    Args:
        user_id: Identificador do usuário.
        payload: Ids dos contexts que o usuário deve poder acessar.

    Raises:
        HTTPException: 404 se o usuário não existir.
    """
    container = get_container()
    if container.user_service.get_by_id(user_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuário não encontrado.")
    container.user_context_service.set_contexts_for_user(user_id, payload.context_ids)
