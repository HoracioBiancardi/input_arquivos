"""Testes do CRUD de contexts, contra o banco de configuração local (SQLite temporário)."""

import pytest
from sqlalchemy import text

from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.models.context import DestinationType, PdfMode, WriteMode
from input_arquivos.backend.security import secret_box
from input_arquivos.backend.services.context_service import ContextService, DuplicateNameError


def test_create_and_get_by_name(session_factory: DatabaseSessionFactory) -> None:
    """Um context criado deve poder ser recuperado pelo nome, com os campos corretos."""
    service = ContextService(session_factory)

    service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )

    context = service.get_by_name("vendas")
    assert context is not None
    assert context.destination_type == DestinationType.MINIO
    assert context.minio_bucket == "vendas"
    assert context.active is True


def test_db_connection_string_is_encrypted_at_rest(session_factory: DatabaseSessionFactory) -> None:
    """`db_connection_string` deve ficar cifrado na tabela `contexts`, mas transparente via ORM.

    Antes desta correção, a senha do banco de destino (embutida na
    connection string) ficava gravada em texto puro em `data/app_config.db`
    — qualquer um com acesso ao arquivo (ou a um backup dele) lia a
    credencial direto, sem precisar de nenhum acesso à aplicação.
    """
    service = ContextService(session_factory)
    plain_connection_string = "mssql+pyodbc://usuario:SenhaSecreta123@host:1433/GOLD"

    created = service.create(
        name="vendas",
        destination_type=DestinationType.SQLSERVER,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        db_connection_string=plain_connection_string,
        db_table="pedidos",
    )

    # Via ORM, o valor continua transparente em texto puro.
    assert created.db_connection_string == plain_connection_string
    fetched = service.get_by_name("vendas")
    assert fetched.db_connection_string == plain_connection_string

    # Mas o valor gravado de fato na tabela não é o texto puro.
    with session_factory.session() as db_session:
        raw_value = db_session.execute(
            text("SELECT db_connection_string FROM contexts WHERE name = 'vendas'")
        ).scalar_one()
    assert raw_value != plain_connection_string
    assert "SenhaSecreta123" not in raw_value
    assert secret_box.decrypt(raw_value) == plain_connection_string


def test_list_active_excludes_inactive_contexts(session_factory: DatabaseSessionFactory) -> None:
    """Contexts desativados não devem aparecer em `list_active`."""
    service = ContextService(session_factory)
    active_context = service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )
    inactive_context = service.create(
        name="estoque",
        destination_type=DestinationType.MINIO,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="estoque",
    )
    service.set_active(inactive_context.id, active=False)

    active_names = [context.name for context in service.list_active()]

    assert active_context.name in active_names
    assert inactive_context.name not in active_names


def test_update_changes_fields(session_factory: DatabaseSessionFactory) -> None:
    """Atualizar um context deve refletir os novos valores ao buscar novamente."""
    service = ContextService(session_factory)
    context = service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )

    service.update(context.id, pdf_mode=PdfMode.RAW_ARCHIVE)

    updated = service.get_by_id(context.id)
    assert updated is not None
    assert updated.pdf_mode == PdfMode.RAW_ARCHIVE


def test_create_with_duplicate_name_raises(session_factory: DatabaseSessionFactory) -> None:
    """Criar um context com um nome já cadastrado deve levantar `DuplicateNameError`."""
    service = ContextService(session_factory)
    service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )

    with pytest.raises(DuplicateNameError):
        service.create(
            name="vendas",
            destination_type=DestinationType.MINIO,
            default_write_mode=WriteMode.APPEND,
            pdf_mode=PdfMode.METADATA_ONLY,
            minio_bucket="outro-bucket",
        )


def test_update_to_duplicate_name_raises(session_factory: DatabaseSessionFactory) -> None:
    """Renomear um context para um nome já usado por outro context deve levantar `DuplicateNameError`."""
    service = ContextService(session_factory)
    service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )
    estoque = service.create(
        name="estoque",
        destination_type=DestinationType.MINIO,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="estoque",
    )

    with pytest.raises(DuplicateNameError):
        service.update(estoque.id, name="vendas")


def test_create_stores_column_rules_json(session_factory: DatabaseSessionFactory) -> None:
    """As regras de validação de dados devem ser persistidas como a string JSON informada."""
    service = ContextService(session_factory)
    rules_json = '[{"column": "valor", "type": "decimal", "required": true}]'

    service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
        column_rules=rules_json,
    )

    stored = service.get_by_name("vendas")
    assert stored is not None
    assert stored.column_rules == rules_json


def test_update_changes_column_rules(session_factory: DatabaseSessionFactory) -> None:
    """Atualizar `column_rules` deve refletir o novo valor ao buscar novamente."""
    service = ContextService(session_factory)
    context = service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )
    assert context.column_rules is None

    new_rules = '[{"column": "produto", "type": "text", "required": false}]'
    service.update(context.id, column_rules=new_rules)

    updated = service.get_by_id(context.id)
    assert updated is not None
    assert updated.column_rules == new_rules


def test_update_keeping_same_name_does_not_raise(session_factory: DatabaseSessionFactory) -> None:
    """Atualizar um context sem trocar o nome não deve ser tratado como duplicidade."""
    service = ContextService(session_factory)
    context = service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        default_write_mode=WriteMode.APPEND,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )

    updated = service.update(context.id, name="vendas", pdf_mode=PdfMode.RAW_ARCHIVE)

    assert updated is not None
    assert updated.pdf_mode == PdfMode.RAW_ARCHIVE
