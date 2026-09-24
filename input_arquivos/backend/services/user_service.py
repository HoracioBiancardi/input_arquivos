"""Serviço de CRUD de usuários (contas de acesso ao sistema)."""

from sqlalchemy import select

from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.models.user import User, UserRole
from input_arquivos.backend.services.auth_service import AuthService


class DuplicateUsernameError(ValueError):
    """Erro levantado ao tentar criar um usuário com um nome de usuário já cadastrado."""


class InvalidCredentialsError(ValueError):
    """Erro levantado quando usuário/senha atual não conferem ao trocar a própria senha."""


class SamePasswordError(ValueError):
    """Erro levantado quando a senha nova é igual à atual."""


class UserService:
    """Gerencia o CRUD de usuários usados no login geral do sistema."""

    def __init__(self, session_factory: DatabaseSessionFactory, auth_service: AuthService) -> None:
        """Inicializa o serviço de usuários.

        Args:
            session_factory: Fábrica de sessões do banco de configuração local.
            auth_service: Serviço de autenticação, usado para gerar hash de senha.
        """
        self._session_factory = session_factory
        self._auth_service = auth_service

    def list_all(self) -> list[User]:
        """Lista todos os usuários cadastrados.

        Returns:
            Lista de usuários ordenada por nome de usuário.
        """
        with self._session_factory.session() as db_session:
            return list(db_session.execute(select(User).order_by(User.username)).scalars().all())

    def get_by_id(self, user_id: int) -> User | None:
        """Busca um usuário pelo identificador interno.

        Args:
            user_id: Identificador do usuário.

        Returns:
            O usuário encontrado, ou `None` se não existir.
        """
        with self._session_factory.session() as db_session:
            return db_session.get(User, user_id)

    def get_by_username(self, username: str) -> User | None:
        """Busca um usuário pelo nome de usuário.

        Args:
            username: Nome de usuário.

        Returns:
            O usuário encontrado, ou `None` se não existir.
        """
        with self._session_factory.session() as db_session:
            return db_session.execute(select(User).where(User.username == username)).scalar_one_or_none()

    def create(
        self, username: str, plain_password: str, role: UserRole, must_change_password: bool = False
    ) -> User:
        """Cria um novo usuário.

        Args:
            username: Nome de usuário único.
            plain_password: Senha em texto puro (será convertida em hash bcrypt).
            role: Papel do usuário (admin ou comum).
            must_change_password: Se a conta nasce marcada para trocar a senha
                (senha inicial definida por um admin).

        Returns:
            O usuário recém-criado.

        Raises:
            DuplicateUsernameError: Se já existir um usuário com esse nome.
        """
        if self.get_by_username(username) is not None:
            raise DuplicateUsernameError(f"Já existe um usuário com o nome '{username}'.")

        user = User(
            username=username,
            password_hash=self._auth_service.hash_password(plain_password),
            role=role,
            active=True,
            must_change_password=must_change_password,
        )
        with self._session_factory.session() as db_session:
            db_session.add(user)
            db_session.flush()
            db_session.refresh(user)
            db_session.expunge(user)
        return user

    def reset_password(self, user_id: int, new_plain_password: str, must_change_password: bool = False) -> None:
        """Redefine a senha de um usuário existente.

        Args:
            user_id: Identificador do usuário.
            new_plain_password: Nova senha em texto puro.
            must_change_password: `True` quando um admin define a senha de
                outra pessoa (o admin conhece essa senha, então o usuário deve
                trocá-la); `False` quando o próprio dono define a senha —
                inclusive zerando a marca da senha padrão do bootstrap.
        """
        with self._session_factory.session() as db_session:
            user = db_session.get(User, user_id)
            if user is not None:
                user.password_hash = self._auth_service.hash_password(new_plain_password)
                user.must_change_password = must_change_password

    def change_own_password(self, username: str, current_password: str, new_password: str) -> None:
        """Troca a senha de um usuário que informou a senha atual.

        A senha atual é validada por `AuthService.authenticate`, então conta
        tentativa errada e respeita o bloqueio temporário, como o login —
        esta rota não vira um atalho para adivinhar senhas.

        Args:
            username: Nome de usuário.
            current_password: Senha atual.
            new_password: Senha nova.

        Raises:
            InvalidCredentialsError: Se usuário/senha atual não conferirem
                (ou a conta estiver inativa).
            AccountLockedError: Se a conta estiver bloqueada por tentativas erradas.
            SamePasswordError: Se a senha nova for igual à atual.
        """
        user = self._auth_service.authenticate(username, current_password)
        if user is None:
            raise InvalidCredentialsError("Usuário ou senha atual inválidos.")
        if new_password == current_password:
            raise SamePasswordError("A senha nova deve ser diferente da atual.")
        self.reset_password(user.id, new_password)

    def set_active(self, user_id: int, active: bool) -> None:
        """Ativa ou desativa a conta de um usuário.

        Args:
            user_id: Identificador do usuário.
            active: Novo estado de ativação.
        """
        with self._session_factory.session() as db_session:
            user = db_session.get(User, user_id)
            if user is not None:
                user.active = active

    def set_role(self, user_id: int, role: UserRole) -> None:
        """Altera o papel (role) de um usuário.

        Args:
            user_id: Identificador do usuário.
            role: Novo papel do usuário.
        """
        with self._session_factory.session() as db_session:
            user = db_session.get(User, user_id)
            if user is not None:
                user.role = role

    def set_last_context(self, user_id: int, context_name: str) -> None:
        """Registra o último context usado pelo usuário, para pré-selecionar na próxima visita.

        Args:
            user_id: Identificador do usuário.
            context_name: Nome do context usado no upload mais recente.
        """
        with self._session_factory.session() as db_session:
            user = db_session.get(User, user_id)
            if user is not None:
                user.last_context_name = context_name
