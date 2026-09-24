"""Tipos Pydantic compartilhados pelos schemas da API."""

from datetime import datetime, timezone
from typing import Annotated

from pydantic import AfterValidator


def _as_utc(value: datetime) -> datetime:
    """Marca como UTC um `datetime` sem fuso (o SQLite não guarda o fuso ao persistir).

    Todos os horários do sistema são gravados em UTC (`datetime.now(timezone.utc)`),
    mas voltam do SQLite "ingênuos". Sem o fuso, a API os serializa sem `+00:00`
    e o navegador os interpreta como hora local — ex.: 17:11 de Brasília
    aparecia como 20:11.

    Args:
        value: Horário lido do banco.

    Returns:
        O mesmo horário, com `tzinfo=UTC` (ou convertido para UTC, se já tinha fuso).
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]
"""`datetime` sempre serializado com fuso UTC explícito (`...+00:00`)."""
