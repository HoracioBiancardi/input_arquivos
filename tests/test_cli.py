"""Testes do console script `input-arquivos` (`input_arquivos/cli.py`)."""

import pytest
from cryptography.fernet import Fernet

from input_arquivos.cli import InputArquivosCli


def test_gerar_chave_prints_valid_fernet_key(capsys: pytest.CaptureFixture[str]) -> None:
    """`gerar-chave` imprime uma linha `CONFIG_ENCRYPTION_KEY=...` com uma chave Fernet utilizável."""
    InputArquivosCli().run(["gerar-chave"])

    first_line = capsys.readouterr().out.splitlines()[0]
    name, key = first_line.split("=", 1)
    assert name == "CONFIG_ENCRYPTION_KEY"
    Fernet(key.encode("ascii"))


def test_gerar_chave_generates_a_different_key_each_time(capsys: pytest.CaptureFixture[str]) -> None:
    """Cada execução gera uma chave nova (nada é reaproveitado de disco)."""
    cli = InputArquivosCli()
    cli.run(["gerar-chave"])
    first = capsys.readouterr().out.splitlines()[0]
    cli.run(["gerar-chave"])
    second = capsys.readouterr().out.splitlines()[0]

    assert first != second


def test_no_command_starts_server(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sem subcomando, o script continua subindo o servidor (comportamento antigo de `uv run input-arquivos`)."""
    calls: list[str] = []
    monkeypatch.setattr(InputArquivosCli, "_serve", lambda self: calls.append("serve"))

    InputArquivosCli().run([])

    assert calls == ["serve"]
