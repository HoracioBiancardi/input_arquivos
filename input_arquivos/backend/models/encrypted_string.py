"""Tipo de coluna SQLAlchemy que cifra/decifra transparentemente uma string em repouso."""

from sqlalchemy.types import String, TypeDecorator

from input_arquivos.backend.security import secret_box


class EncryptedString(TypeDecorator):
    """Coluna `String` cifrada em repouso via `security.secret_box` (Fernet).

    Transparente para o resto do código: qualquer leitura/escrita de um
    atributo mapeado com este tipo já trabalha com o valor em texto puro —
    a cifragem/decifragem acontece só na fronteira com o banco
    (`process_bind_param`/`process_result_value`), então nenhum service ou
    rota precisa saber que o valor está cifrado em disco.

    Trata um valor legado em texto puro (gravado antes deste tipo existir)
    como texto puro na leitura, em vez de levantar `InvalidToken` — evita
    quebrar a aplicação para linhas antigas ainda não migradas; ver
    `db/bootstrap.py::_encrypt_legacy_plaintext_secrets` para a migração
    que re-grava essas linhas já cifradas.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect: object) -> str | None:
        """Cifra o valor antes de gravar no banco."""
        if value is None:
            return None
        return secret_box.encrypt(value)

    def process_result_value(self, value: str | None, dialect: object) -> str | None:
        """Decifra o valor lido do banco; repassa como está se não for um token Fernet válido (dado legado)."""
        if value is None:
            return None
        if not secret_box.is_valid_ciphertext(value):
            return value
        return secret_box.decrypt(value)
