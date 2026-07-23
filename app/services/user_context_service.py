"""Serviço de controle de acesso: quais contexts cada usuário comum pode ver e usar na tela de upload."""

from sqlalchemy import delete, insert, select

from app.db.session import DatabaseSessionFactory
from app.models.context import Context
from app.models.user import User, UserRole
from app.models.user_context_access import user_context_access
from app.services.context_service import ContextService


class UserContextService:
    """Gerencia quais contexts um usuário comum pode acessar, e resolve a lista final por usuário.

    Usuários com `role=admin` sempre têm acesso a todos os contexts ativos,
    então as operações de leitura/atribuição desta classe só têm efeito
    prático sobre usuários com `role=user`.
    """

    def __init__(self, session_factory: DatabaseSessionFactory, context_service: ContextService) -> None:
        """Inicializa o serviço de controle de acesso.

        Args:
            session_factory: Fábrica de sessões do banco de configuração local.
            context_service: Serviço usado para resolver contexts por id/listar os ativos.
        """
        self._session_factory = session_factory
        self._context_service = context_service

    def list_context_ids_for_user(self, user_id: int) -> list[int]:
        """Lista os ids dos contexts explicitamente liberados para um usuário.

        Args:
            user_id: Identificador do usuário.

        Returns:
            Lista de ids de contexts liberados (vazia se nenhum foi atribuído ainda).
        """
        with self._session_factory.session() as db_session:
            query = select(user_context_access.c.context_id).where(user_context_access.c.user_id == user_id)
            return [row[0] for row in db_session.execute(query).all()]

    def set_contexts_for_user(self, user_id: int, context_ids: list[int]) -> None:
        """Substitui a lista de contexts liberados para um usuário.

        Args:
            user_id: Identificador do usuário.
            context_ids: Ids dos contexts que o usuário deve poder acessar.
        """
        with self._session_factory.session() as db_session:
            db_session.execute(delete(user_context_access).where(user_context_access.c.user_id == user_id))
            if context_ids:
                db_session.execute(
                    insert(user_context_access),
                    [{"user_id": user_id, "context_id": context_id} for context_id in context_ids],
                )

    def list_accessible_contexts(self, user: User) -> list[Context]:
        """Lista os contexts ativos que um usuário pode acessar na tela de upload.

        Admins sempre veem todos os contexts ativos. Usuários comuns veem
        apenas os contexts ativos que lhes foram explicitamente liberados.

        Args:
            user: Usuário autenticado.

        Returns:
            Lista de contexts ativos acessíveis para este usuário, ordenada por nome.
        """
        active_contexts = self._context_service.list_active()
        if user.role == UserRole.ADMIN:
            return active_contexts

        allowed_ids = set(self.list_context_ids_for_user(user.id))
        return [context for context in active_contexts if context.id in allowed_ids]
