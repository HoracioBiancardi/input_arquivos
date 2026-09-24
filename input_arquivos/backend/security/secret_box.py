"""Criptografia simétrica para dados sensíveis persistidos no banco local.

Usado para cifrar em repouso as credenciais globais do MinIO cadastradas via
`/admin/settings` (`SystemSettings.minio_access_key`/`minio_secret_key`).
A chave vem, nesta ordem, de:

1. `CONFIG_ENCRYPTION_KEY` (variável de ambiente/.env), gerada com
   `uv run input-arquivos gerar-chave` — recomendado em produção, porque tira
   a chave da mesma pasta do banco cifrado;
2. o arquivo `data/.config_encryption_key` ao lado do banco local, gerado
   automaticamente (0600) na primeira execução se não existir — mesma
   estratégia de `session_secret` em `auth/session.py`, mantida para
   desenvolvimento local e instalações antigas.
"""

from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from input_arquivos.backend.config import Settings, get_settings

_KEY_FILENAME = ".config_encryption_key"


class InvalidEncryptionKeyError(ValueError):
    """Erro levantado quando `CONFIG_ENCRYPTION_KEY` não é uma chave Fernet válida."""


def generate_key() -> str:
    """Gera uma chave Fernet nova, pronta para colar em `CONFIG_ENCRYPTION_KEY`.

    Returns:
        Chave Fernet (32 bytes em base64 url-safe), como texto.
    """
    return Fernet.generate_key().decode("ascii")


def _resolve_encryption_key(settings: Settings) -> bytes:
    """Resolve a chave Fernet usada para cifrar segredos de configuração em repouso.

    Args:
        settings: Configurações da aplicação.

    Returns:
        Chave Fernet (32 bytes url-safe base64): a de `CONFIG_ENCRYPTION_KEY`
        se configurada; senão a lida de `data/.config_encryption_key`, ou
        gerada e persistida nesse arquivo (permissão 0600) na primeira execução.

    Raises:
        InvalidEncryptionKeyError: Se `CONFIG_ENCRYPTION_KEY` estiver
            preenchida com algo que não é uma chave Fernet.
    """
    if settings.config_encryption_key:
        key = settings.config_encryption_key.strip()
        try:
            Fernet(key)
        except ValueError as error:
            raise InvalidEncryptionKeyError(
                "CONFIG_ENCRYPTION_KEY não é uma chave válida. Gere uma com: uv run input-arquivos gerar-chave"
            ) from error
        return key.encode("ascii")

    key_path = Path(settings.app_config_db_path).parent / _KEY_FILENAME
    if key_path.exists():
        return key_path.read_bytes().strip()

    key_path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    key_path.chmod(0o600)
    return key


_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    """Retorna a instância (cacheada) do Fernet usado para cifrar/decifrar segredos."""
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_resolve_encryption_key(get_settings()))
    return _fernet


def encrypt(plaintext: str) -> str:
    """Cifra uma string, para persistir em repouso.

    Args:
        plaintext: Valor em texto puro (ex.: connection string, secret key).

    Returns:
        Token Fernet (texto ASCII), seguro para gravar numa coluna `String`.
    """
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decifra um token Fernet gerado por `encrypt`.

    Args:
        ciphertext: Token Fernet retornado por `encrypt`.

    Returns:
        O valor original em texto puro.

    Raises:
        InvalidToken: Se `ciphertext` não for um token Fernet válido para a
            chave atual (corrompido, ou cifrado com outra chave).
    """
    return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")


def is_valid_ciphertext(value: str) -> bool:
    """Verifica se um valor já é um token Fernet válido para a chave atual.

    Usado só para migrar dados legados gravados em texto puro antes desta
    cifragem existir: distingue um valor já cifrado de um valor antigo ainda
    em texto puro, sem precisar de uma coluna extra de metadado.

    Args:
        value: Valor lido do banco.

    Returns:
        `True` se `value` decifra com sucesso (já está cifrado), `False`
        caso contrário (provavelmente texto puro legado).
    """
    try:
        _get_fernet().decrypt(value.encode("ascii"))
        return True
    except (InvalidToken, ValueError):
        return False


def reset_for_testing() -> None:
    """Limpa o cache do Fernet, para testes que trocam `app_config_db_path` entre execuções."""
    global _fernet
    _fernet = None
