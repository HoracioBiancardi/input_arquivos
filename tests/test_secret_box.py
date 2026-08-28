"""Testes do secret_box: cifragem/decifragem de segredos de configuração e persistência da chave."""

from pathlib import Path

import pytest

from input_arquivos.backend.config import get_settings
from input_arquivos.backend.security import secret_box


@pytest.fixture(autouse=True)
def _isolate_secret_box(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isola cada teste num `tmp_path` próprio, para não reaproveitar a chave entre testes."""
    monkeypatch.setenv("APP_CONFIG_DB_PATH", str(tmp_path / "app.db"))
    get_settings.cache_clear()
    secret_box.reset_for_testing()
    yield
    get_settings.cache_clear()
    secret_box.reset_for_testing()


def test_encrypt_decrypt_roundtrip() -> None:
    """Um valor cifrado deve decifrar de volta exatamente igual."""
    plaintext = "S3gr3d0!C0mplic4do"

    ciphertext = secret_box.encrypt(plaintext)

    assert ciphertext != plaintext
    assert secret_box.decrypt(ciphertext) == plaintext


def test_key_is_generated_and_persisted(tmp_path: Path) -> None:
    """A chave deve ser gerada na primeira cifragem e persistida em disco com permissão restrita."""
    secret_box.encrypt("qualquer valor")

    key_path = tmp_path / ".config_encryption_key"
    assert key_path.exists()
    assert oct(key_path.stat().st_mode)[-3:] == "600"


def test_key_is_reused_across_resets(tmp_path: Path) -> None:
    """Reiniciar o cache em memória não deve gerar uma chave nova se já existe uma em disco."""
    ciphertext = secret_box.encrypt("valor-fixo")

    secret_box.reset_for_testing()

    assert secret_box.decrypt(ciphertext) == "valor-fixo"


def test_is_valid_ciphertext_distinguishes_legacy_plaintext() -> None:
    """`is_valid_ciphertext` deve distinguir um token Fernet real de um valor legado em texto puro."""
    ciphertext = secret_box.encrypt("segredo")

    assert secret_box.is_valid_ciphertext(ciphertext) is True
    assert secret_box.is_valid_ciphertext("um-valor-qualquer-em-texto-puro") is False
