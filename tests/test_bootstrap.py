"""Testes do DatabaseBootstrapper: seed do admin e migração de segredos legados em texto puro."""

from sqlalchemy import text

from input_arquivos.backend.db.bootstrap import DatabaseBootstrapper
from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.security import secret_box
from input_arquivos.backend.services.auth_service import AuthService


def test_legacy_plaintext_connection_string_gets_encrypted(session_factory: DatabaseSessionFactory) -> None:
    """Um `db_connection_string` gravado em texto puro (dado legado) deve ser cifrado no próximo bootstrap.

    Simula o estado de antes desta correção existir: insere a linha via SQL
    bruto (bypassando `EncryptedString`), como se tivesse sido gravada por
    uma versão anterior do código.
    """
    bootstrapper = DatabaseBootstrapper(session_factory, AuthService(session_factory))
    bootstrapper.run()  # cria as tabelas e semeia o admin

    plain_connection_string = "mssql+pyodbc://user:SenhaLegada123@host:1433/GOLD"
    with session_factory.session() as db_session:
        db_session.execute(
            text(
                "INSERT INTO contexts "
                "(name, destination_type, db_connection_string, db_schema_name, default_write_mode, "
                "pdf_mode, image_mode, allowed_file_types, active, created_at, updated_at) "
                "VALUES (:name, 'sqlserver', :conn, 'dbo', 'append', 'metadata_only', 'raw_archive', "
                "'csv', 1, datetime('now'), datetime('now'))"
            ),
            {"name": "legado", "conn": plain_connection_string},
        )

    # Confirma que a linha realmente está em texto puro antes da migração.
    with session_factory.session() as db_session:
        raw_before = db_session.execute(
            text("SELECT db_connection_string FROM contexts WHERE name = 'legado'")
        ).scalar_one()
    assert raw_before == plain_connection_string

    bootstrapper.run()

    with session_factory.session() as db_session:
        raw_after = db_session.execute(
            text("SELECT db_connection_string FROM contexts WHERE name = 'legado'")
        ).scalar_one()
    assert raw_after != plain_connection_string
    assert secret_box.decrypt(raw_after) == plain_connection_string


def test_migration_is_idempotent_for_already_encrypted_rows(session_factory: DatabaseSessionFactory) -> None:
    """Rodar o bootstrap de novo não deve recifrar (nem quebrar) uma linha já cifrada."""
    bootstrapper = DatabaseBootstrapper(session_factory, AuthService(session_factory))
    bootstrapper.run()

    with session_factory.session() as db_session:
        db_session.execute(
            text(
                "INSERT INTO contexts "
                "(name, destination_type, db_connection_string, db_schema_name, default_write_mode, "
                "pdf_mode, image_mode, allowed_file_types, active, created_at, updated_at) "
                "VALUES ('ja_cifrado', 'sqlserver', :conn, 'dbo', 'append', 'metadata_only', 'raw_archive', "
                "'csv', 1, datetime('now'), datetime('now'))"
            ),
            {"conn": secret_box.encrypt("mssql+pyodbc://user:pass@host/db")},
        )

    bootstrapper.run()
    bootstrapper.run()

    with session_factory.session() as db_session:
        raw_value = db_session.execute(
            text("SELECT db_connection_string FROM contexts WHERE name = 'ja_cifrado'")
        ).scalar_one()
    assert secret_box.decrypt(raw_value) == "mssql+pyodbc://user:pass@host/db"
