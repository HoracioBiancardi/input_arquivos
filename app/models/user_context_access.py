"""Tabela de associação entre usuários e os contexts que cada um pode acessar na tela de upload."""

from sqlalchemy import Column, ForeignKey, Integer, Table

from app.models.base import Base

user_context_access = Table(
    "user_context_access",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id"), primary_key=True),
    Column("context_id", Integer, ForeignKey("contexts.id"), primary_key=True),
)
"""Associação N:N: quais contexts (`context_id`) cada usuário comum (`user_id`) pode usar.

Usuários com `role=admin` sempre têm acesso a todos os contexts ativos,
independente do que estiver registrado aqui — esta tabela só restringe
usuários comuns.
"""
