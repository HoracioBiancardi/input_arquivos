"""Testes do CRUD de contexts, contra o banco de configuração local (SQLite temporário)."""

import pytest

from app.db.session import DatabaseSessionFactory
from app.models.context import DestinationType, PdfMode, WriteMode
from app.services.context_service import ContextService, DuplicateNameError


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
