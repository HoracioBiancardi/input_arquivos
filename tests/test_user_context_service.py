"""Testes do UserContextService: controle de quais contexts cada usuário comum pode acessar."""

from app.db.session import DatabaseSessionFactory
from app.models.context import DestinationType, PdfMode, WriteMode
from app.models.user import UserRole
from app.services.auth_service import AuthService
from app.services.context_service import ContextService
from app.services.user_context_service import UserContextService
from app.services.user_service import UserService


def _make_services(session_factory: DatabaseSessionFactory) -> tuple[ContextService, UserService, UserContextService]:
    """Monta o conjunto de serviços necessários para os testes deste arquivo."""
    context_service = ContextService(session_factory)
    auth_service = AuthService(session_factory)
    user_service = UserService(session_factory, auth_service)
    user_context_service = UserContextService(session_factory, context_service)
    return context_service, user_service, user_context_service


def test_admin_sees_all_active_contexts_regardless_of_assignment(session_factory: DatabaseSessionFactory) -> None:
    """Usuários admin devem ver todos os contexts ativos, mesmo sem nenhuma atribuição explícita."""
    context_service, user_service, user_context_service = _make_services(session_factory)
    context = context_service.create(
        name="vendas",
        destination_type=DestinationType.LOCAL,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
    )
    admin = user_service.create(username="admin", plain_password="123456", role=UserRole.ADMIN)

    accessible = user_context_service.list_accessible_contexts(admin)

    assert [c.name for c in accessible] == [context.name]


def test_regular_user_sees_only_assigned_contexts(session_factory: DatabaseSessionFactory) -> None:
    """Usuários comuns só devem ver os contexts explicitamente liberados para eles."""
    context_service, user_service, user_context_service = _make_services(session_factory)
    vendas = context_service.create(
        name="vendas",
        destination_type=DestinationType.LOCAL,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
    )
    context_service.create(
        name="estoque",
        destination_type=DestinationType.LOCAL,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
    )
    user = user_service.create(username="maria", plain_password="123456", role=UserRole.USER)

    user_context_service.set_contexts_for_user(user.id, [vendas.id])
    accessible = user_context_service.list_accessible_contexts(user)

    assert [c.name for c in accessible] == ["vendas"]


def test_set_contexts_for_user_replaces_previous_assignment(session_factory: DatabaseSessionFactory) -> None:
    """Atribuir uma nova lista de contexts deve substituir a anterior, não acumular."""
    context_service, user_service, user_context_service = _make_services(session_factory)
    vendas = context_service.create(
        name="vendas",
        destination_type=DestinationType.LOCAL,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
    )
    estoque = context_service.create(
        name="estoque",
        destination_type=DestinationType.LOCAL,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
    )
    user = user_service.create(username="maria", plain_password="123456", role=UserRole.USER)

    user_context_service.set_contexts_for_user(user.id, [vendas.id, estoque.id])
    user_context_service.set_contexts_for_user(user.id, [estoque.id])

    assert user_context_service.list_context_ids_for_user(user.id) == [estoque.id]


def test_user_without_any_assignment_sees_no_contexts(session_factory: DatabaseSessionFactory) -> None:
    """Um usuário comum recém-criado, sem nenhuma atribuição, não deve ver nenhum context."""
    context_service, user_service, user_context_service = _make_services(session_factory)
    context_service.create(
        name="vendas",
        destination_type=DestinationType.LOCAL,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
    )
    user = user_service.create(username="maria", plain_password="123456", role=UserRole.USER)

    assert user_context_service.list_accessible_contexts(user) == []
