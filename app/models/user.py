"""Modelo ORM de User: contas de acesso ao sistema (usuários comuns e admins)."""

import enum
from datetime import datetime, timezone

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserRole(str, enum.Enum):
    """Papel de um usuário no sistema."""

    ADMIN = "admin"
    USER = "user"


class User(Base):
    """Conta de acesso ao sistema, usada tanto pela tela de upload quanto pela área admin.

    Attributes:
        id: Identificador interno do usuário.
        username: Nome de usuário único, usado no login.
        password_hash: Hash bcrypt da senha do usuário.
        role: Papel do usuário (admin tem acesso à área administrativa e a
            todos os contexts, independente do que estiver liberado explicitamente).
        active: Indica se a conta pode ser usada para login.
        last_context_name: Nome do último context usado por este usuário na tela
            de upload, pré-selecionado automaticamente na próxima visita.
        created_at: Data de criação da conta.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(SqlEnum(UserRole), default=UserRole.USER)
    active: Mapped[bool] = mapped_column(default=True)
    last_context_name: Mapped[str | None] = mapped_column(String(100), default=None)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
