"""Testes do CRUD de contexts, contra o banco de configuração local (SQLite temporário)."""

import pytest

from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.models.context import Context, DestinationType, PdfMode
from input_arquivos.backend.services import context_service as context_service_module
from input_arquivos.backend.services.context_service import (
    ContextService,
    DatabaseSchemaError,
    DuplicateNameError,
    MinioBucketError,
)


class _FakeMinioClient:
    """Dublê do client MinIO, sem I/O de rede, para isolar os testes de CRUD de contexts."""

    def __init__(self, existing_buckets: set[str] | None = None, fail: bool = False) -> None:
        self.existing_buckets = existing_buckets or set()
        self.created_buckets: list[str] = []
        self.fail = fail

    def bucket_exists(self, bucket: str) -> bool:
        if self.fail:
            raise RuntimeError("conexão recusada")
        return bucket in self.existing_buckets

    def make_bucket(self, bucket: str) -> None:
        self.created_buckets.append(bucket)
        self.existing_buckets.add(bucket)


@pytest.fixture(autouse=True)
def fake_minio_client(monkeypatch: pytest.MonkeyPatch) -> _FakeMinioClient:
    """Substitui `build_minio_client` por um dublê, para todos os testes deste módulo.

    Sem isso, todo `create`/`update` de um context MINIO tentaria conectar a
    um MinIO real (já que agora criam o bucket automaticamente).
    """
    client = _FakeMinioClient()
    monkeypatch.setattr(context_service_module, "build_minio_client", lambda: client)
    return client


def test_create_and_get_by_name(session_factory: DatabaseSessionFactory) -> None:
    """Um context criado deve poder ser recuperado pelo nome, com os campos corretos."""
    service = ContextService(session_factory)

    service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
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
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )
    inactive_context = service.create(
        name="estoque",
        destination_type=DestinationType.MINIO,
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
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )

    with pytest.raises(DuplicateNameError):
        service.create(
            name="vendas",
            destination_type=DestinationType.MINIO,
            pdf_mode=PdfMode.METADATA_ONLY,
            minio_bucket="outro-bucket",
        )


def test_update_to_duplicate_name_raises(session_factory: DatabaseSessionFactory) -> None:
    """Renomear um context para um nome já usado por outro context deve levantar `DuplicateNameError`."""
    service = ContextService(session_factory)
    service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )
    estoque = service.create(
        name="estoque",
        destination_type=DestinationType.MINIO,
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
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )

    updated = service.update(context.id, name="vendas", pdf_mode=PdfMode.RAW_ARCHIVE)

    assert updated is not None
    assert updated.pdf_mode == PdfMode.RAW_ARCHIVE


def test_create_creates_minio_bucket_when_missing(
    session_factory: DatabaseSessionFactory, fake_minio_client: _FakeMinioClient
) -> None:
    """Criar um context MINIO deve criar o bucket no MinIO se ele ainda não existir."""
    service = ContextService(session_factory)

    service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )

    assert fake_minio_client.created_buckets == ["vendas"]


def test_create_does_not_recreate_existing_bucket(
    session_factory: DatabaseSessionFactory, fake_minio_client: _FakeMinioClient
) -> None:
    """Criar um context com um bucket que já existe no MinIO não deve chamar `make_bucket`."""
    fake_minio_client.existing_buckets.add("vendas")
    service = ContextService(session_factory)

    service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )

    assert fake_minio_client.created_buckets == []


def test_create_local_context_does_not_touch_minio(
    session_factory: DatabaseSessionFactory, fake_minio_client: _FakeMinioClient
) -> None:
    """Criar um context do tipo LOCAL não deve tentar criar bucket nenhum."""
    fake_minio_client.fail = True
    service = ContextService(session_factory)

    service.create(
        name="vendas",
        destination_type=DestinationType.LOCAL,
        pdf_mode=PdfMode.METADATA_ONLY,
        local_path="/tmp/vendas",
    )

    assert fake_minio_client.created_buckets == []


def test_create_raises_and_does_not_persist_when_minio_unreachable(
    session_factory: DatabaseSessionFactory, fake_minio_client: _FakeMinioClient
) -> None:
    """Se o MinIO estiver inacessível, `create` deve levantar `MinioBucketError` e não salvar o context."""
    fake_minio_client.fail = True
    service = ContextService(session_factory)

    with pytest.raises(MinioBucketError):
        service.create(
            name="vendas",
            destination_type=DestinationType.MINIO,
            pdf_mode=PdfMode.METADATA_ONLY,
            minio_bucket="vendas",
        )

    assert service.get_by_name("vendas") is None


def test_update_creates_bucket_when_bucket_changes(
    session_factory: DatabaseSessionFactory, fake_minio_client: _FakeMinioClient
) -> None:
    """Trocar o bucket de um context existente deve criar o novo bucket, se necessário."""
    service = ContextService(session_factory)
    context = service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )

    service.update(
        context.id,
        name="vendas",
        destination_type=DestinationType.MINIO,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas-novo",
    )

    assert "vendas-novo" in fake_minio_client.created_buckets


def test_set_active_does_not_require_minio_connectivity(
    session_factory: DatabaseSessionFactory, fake_minio_client: _FakeMinioClient
) -> None:
    """Ativar/desativar um context não deve depender do MinIO estar acessível."""
    service = ContextService(session_factory)
    context = service.create(
        name="vendas",
        destination_type=DestinationType.MINIO,
        pdf_mode=PdfMode.METADATA_ONLY,
        minio_bucket="vendas",
    )

    fake_minio_client.fail = True

    service.set_active(context.id, active=False)

    updated = service.get_by_id(context.id)
    assert updated is not None
    assert updated.active is False


class _FakeSchemaLoader:
    """Loader falso que só registra os schemas pedidos (ou falha, se configurado)."""

    def __init__(self, error: Exception | None = None) -> None:
        self.schemas: list[str] = []
        self._error = error

    def ensure_schema(self, schema: str) -> None:
        if self._error is not None:
            raise self._error
        self.schemas.append(schema)


def _create_loading_context(service: ContextService, **overrides: object) -> Context:
    fields = {
        "name": "meta",
        "destination_type": DestinationType.LOCAL,
        "pdf_mode": PdfMode.METADATA_ONLY,
        "local_path": "data/local",
        "load_to_database": True,
        "db_schema": "inputarquivos",
    }
    fields.update(overrides)
    return service.create(**fields)


def test_create_with_schema_creates_it_in_database(session_factory: DatabaseSessionFactory) -> None:
    """Salvar um context com carga e schema cria o schema no banco na hora."""
    loader = _FakeSchemaLoader()
    _create_loading_context(ContextService(session_factory, loader))

    assert loader.schemas == ["inputarquivos"]


def test_create_without_load_or_schema_does_not_touch_database(session_factory: DatabaseSessionFactory) -> None:
    """Sem carga ligada, ou sem schema (usa o padrão), nada é criado."""
    loader = _FakeSchemaLoader()
    service = ContextService(session_factory, loader)
    _create_loading_context(service, name="a", load_to_database=False)
    _create_loading_context(service, name="b", db_schema=None)

    assert loader.schemas == []


def test_update_only_recreates_schema_when_it_changes(session_factory: DatabaseSessionFactory) -> None:
    """Salvar só regras/nome não toca no banco; trocar o schema cria o novo."""
    loader = _FakeSchemaLoader()
    service = ContextService(session_factory, loader)
    context = _create_loading_context(service)

    service.update(context.id, load_to_database=True, db_schema="inputarquivos", column_rules=None)
    service.update(context.id, load_to_database=True, db_schema="staging")

    assert loader.schemas == ["inputarquivos", "staging"]


def test_schema_creation_failure_blocks_save(session_factory: DatabaseSessionFactory) -> None:
    """Sem permissão para criar o schema, o context não é salvo e o erro sobe com o motivo."""
    service = ContextService(session_factory, _FakeSchemaLoader(error=RuntimeError("permission denied")))

    with pytest.raises(DatabaseSchemaError, match="permission denied"):
        _create_loading_context(service)
    assert service.get_by_name("meta") is None
