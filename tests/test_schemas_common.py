"""Testes do `UtcDatetime`: horários do SQLite (sem fuso) saem da API marcados como UTC."""

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from input_arquivos.backend.schemas.common import UtcDatetime


class _Model(BaseModel):
    when: UtcDatetime


def test_naive_datetime_is_serialized_as_utc() -> None:
    """Sem fuso (como volta do SQLite), vira UTC explícito — o navegador converte para Brasília."""
    serialized = _Model(when=datetime(2026, 9, 24, 20, 11, 34)).model_dump_json()

    assert '"2026-09-24T20:11:34Z"' in serialized


def test_aware_datetime_is_converted_to_utc() -> None:
    """Com outro fuso, converte para UTC em vez de só trocar o rótulo."""
    brasilia = timezone(timedelta(hours=-3))

    model = _Model(when=datetime(2026, 9, 24, 17, 11, tzinfo=brasilia))

    assert model.when == datetime(2026, 9, 24, 20, 11, tzinfo=timezone.utc)
