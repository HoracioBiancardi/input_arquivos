"""Base declarativa compartilhada pelos modelos ORM da aplicação."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Classe base declarativa do SQLAlchemy para todos os modelos da aplicação."""
