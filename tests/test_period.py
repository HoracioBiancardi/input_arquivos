"""Testes do controle por mês de competência: leitura do mês, mês repetido, carga por mês e grade de meses."""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.destinations.registry import DestinationWriterRegistry
from input_arquivos.backend.ingestion.pipeline import IngestionPipeline
from input_arquivos.backend.loaders.database_loader import DatabaseLoader
from input_arquivos.backend.models.context import (
    Context,
    DestinationType,
    DuplicatePolicy,
    PdfMode,
    PeriodMode,
    PeriodSource,
)
from input_arquivos.backend.models.upload_history import LoadStatus, UploadHistory, UploadStatus
from input_arquivos.backend.services.context_service import ContextService
from input_arquivos.backend.services.period import (
    PeriodError,
    build_year_grid,
    current_period,
    period_label,
    resolve_period,
)
from input_arquivos.backend.services.upload_service import PeriodAlreadySentError, UploadService
from tests.test_security_regressions import _create_user, _login, _reset_app_state


def _context(**fields: object) -> Context:
    defaults = {
        "name": "metas",
        "period_mode": PeriodMode.MONTHLY,
        "period_source": PeriodSource.SELECTOR,
        "created_at": datetime(2026, 2, 15, tzinfo=timezone.utc),
    }
    return Context(**{**defaults, **fields})


# ── Leitura do mês ───────────────────────────────────────────────────────


def test_context_without_monthly_mode_has_no_period() -> None:
    assert resolve_period(_context(period_mode=PeriodMode.NONE), None, "2026-10") is None


def test_selector_requires_a_valid_month() -> None:
    context = _context()
    assert resolve_period(context, None, "2026-10") == "2026-10"
    for informed in (None, "", "2026-13", "10/2026"):
        with pytest.raises(PeriodError, match="Informe o mês"):
            resolve_period(context, None, informed)


def test_column_month_comes_from_the_dates_in_the_file() -> None:
    context = _context(period_source=PeriodSource.COLUMN, period_column="Data")
    dataframe = pd.DataFrame({"Data": ["01/10/2026", "31/10/2026", 46296], "meta": [1, 2, 3]})  # 46296 = 01/10/2026

    assert resolve_period(context, dataframe, "2020-01") == "2026-10"


@pytest.mark.parametrize(
    ("dataframe", "message"),
    [
        (pd.DataFrame({"outra": [1]}), "não tem a coluna 'Data'"),
        (pd.DataFrame({"Data": ["01/10/2026", ""]}), "1 linha\\(s\\) sem data"),
        (pd.DataFrame({"Data": ["01/10/2026", "abc"]}), "1 linha\\(s\\) com data inválida"),
        (pd.DataFrame({"Data": ["01/10/2026", "01/11/2026"]}), "2 meses .*outubro/2026, novembro/2026"),
        (None, "precisa ter uma tabela"),
    ],
)
def test_column_mode_rejects_files_without_a_single_month(dataframe: pd.DataFrame | None, message: str) -> None:
    context = _context(period_source=PeriodSource.COLUMN, period_column="Data")
    with pytest.raises(PeriodError, match=message):
        resolve_period(context, dataframe, None)


def test_period_label_and_current_period_in_brasilia() -> None:
    assert period_label("2026-03") == "março/2026"
    # 01/11 às 01:00 UTC ainda é 31/10 em Brasília.
    assert current_period(datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc)) == "2026-10"


# ── Grade de meses ───────────────────────────────────────────────────────


def test_year_grid_marks_sent_missing_future_and_not_expected() -> None:
    context = _context(period_start="2026-03")
    uploads = [
        UploadHistory(id=1, period="2026-04", superseded_by=2),
        UploadHistory(id=2, period="2026-04", superseded_by=None),
        UploadHistory(id=3, period="2026-12", superseded_by=None),
    ]

    months = {month.period: month for month in build_year_grid(context, uploads, 2026, "2026-10")}

    assert months["2026-02"].state == "not_expected"
    assert months["2026-03"].state == "missing"
    assert months["2026-04"].state == "sent"
    assert [upload.id for upload in months["2026-04"].current] == [2]
    assert months["2026-04"].version_count == 2
    assert months["2026-10"].state == "missing"
    assert months["2026-11"].state == "future"
    assert months["2026-12"].state == "sent"  # metas enviadas antes do mês


def test_year_grid_without_start_uses_context_creation_month() -> None:
    months = build_year_grid(_context(), [], 2026, "2026-10")
    assert [month.state for month in months[:2]] == ["not_expected", "missing"]


# ── Mês repetido e carga por mês ─────────────────────────────────────────


@pytest.fixture
def monthly(session_factory: DatabaseSessionFactory, tmp_path: Path):
    """`UploadService` com um context mensal (mês informado no envio) que carrega num SQLite de destino."""
    context_service = ContextService(session_factory)
    context_service.create(
        name="metas",
        destination_type=DestinationType.LOCAL,
        pdf_mode=PdfMode.RAW_ARCHIVE,
        local_path=str(tmp_path / "arquivos"),
        load_to_database=True,
        period_mode=PeriodMode.MONTHLY,
        period_source=PeriodSource.SELECTOR,
    )
    target_url = f"sqlite:///{tmp_path / 'destino.db'}"
    service = UploadService(
        session_factory=session_factory,
        context_service=context_service,
        pipeline=IngestionPipeline(),
        writer_registry=DestinationWriterRegistry(),
        database_loader=DatabaseLoader(lambda: target_url),
    )
    return service, context_service, target_url


def _csv(*metas: int) -> bytes:
    return pd.DataFrame({"vendedor": [f"V{i}" for i in range(len(metas))], "meta": list(metas)}).to_csv(
        index=False
    ).encode("utf-8")


def _table(url: str, name: str = "metas") -> pd.DataFrame:
    engine = create_engine(url)
    try:
        return pd.read_sql_table(name, engine)
    finally:
        engine.dispose()


def test_resending_a_month_requires_confirmation_and_replaces_only_that_month(monthly) -> None:
    service, _, url = monthly
    october = service.process_upload(_csv(10, 20), "out.csv", "metas", "maria", period="2026-10")
    november = service.process_upload(_csv(5), "nov.csv", "metas", "maria", period="2026-11")

    with pytest.raises(PeriodAlreadySentError, match="outubro/2026 já foi enviado por maria"):
        service.process_upload(_csv(99), "out_v2.csv", "metas", "joao", period="2026-10")
    assert len(_table(url)) == 3  # nada mudou sem a confirmação

    resent = service.process_upload(_csv(30), "out_v2.csv", "metas", "joao", period="2026-10", replace_period=True)

    table = _table(url)
    assert sorted(table["meta"].tolist()) == [5, 30]
    assert set(table["id_envio"]) == {november.id, resent.id}
    assert set(pd.to_datetime(table["competencia_envio"]).dt.strftime("%Y-%m")) == {"2026-10", "2026-11"}
    old = service._get_history(october.id)
    assert old.superseded_by == resent.id
    assert old.load_status == LoadStatus.SUPERSEDED
    assert service.find_current_upload(service.resolve_context("metas"), "2026-10").id == resent.id


def test_block_policy_rejects_a_second_upload_of_the_month(monthly) -> None:
    service, context_service, url = monthly
    context_service.update(service.resolve_context("metas").id, duplicate_policy=DuplicatePolicy.BLOCK)
    service.process_upload(_csv(10), "out.csv", "metas", "maria", period="2026-10")

    rejected = service.process_upload(_csv(99), "out_v2.csv", "metas", "joao", period="2026-10", replace_period=True)

    assert rejected.status == UploadStatus.ERROR
    assert "não aceita reenviar" in rejected.error_message
    assert _table(url)["meta"].tolist() == [10]


def test_allow_policy_accumulates_uploads_of_the_same_month(monthly) -> None:
    service, context_service, url = monthly
    context_service.update(service.resolve_context("metas").id, duplicate_policy=DuplicatePolicy.ALLOW)
    first = service.process_upload(_csv(10), "filial_a.csv", "metas", "maria", period="2026-10")
    service.process_upload(_csv(20), "filial_b.csv", "metas", "joao", period="2026-10")

    assert sorted(_table(url)["meta"].tolist()) == [10, 20]
    assert service._get_history(first.id).superseded_by is None


def test_missing_month_becomes_an_error_in_the_audit_log(monthly) -> None:
    service, _, url = monthly
    history = service.process_upload(_csv(10), "out.csv", "metas", "maria")

    assert history.status == UploadStatus.ERROR
    assert "Informe o mês" in history.error_message


def test_late_load_of_an_older_upload_does_not_overwrite_the_newer_one(monthly) -> None:
    """A carga em background do envio antigo chega depois da do novo: o novo fica na tabela."""
    service, _, url = monthly
    context = service.resolve_context("metas")
    artifact, period = service.apply_period(context, service.build_artifact(_csv(10), "a.csv", context, "maria"), "2026-10")
    first = service.finalize(artifact, context, "a.csv", "maria", period)  # carga fica pendente
    first_bytes = artifact.artifact_bytes
    second = service.process_upload(_csv(30), "b.csv", "metas", "joao", period="2026-10", replace_period=True)

    late = service.run_database_load(first.id, first_bytes)
    skipped = DatabaseLoader(lambda: url).load(first_bytes, context, first.id, period="2026-10")

    assert late.load_status == LoadStatus.SUPERSEDED
    assert skipped.skipped
    assert _table(url)["id_envio"].tolist() == [second.id]


def test_month_column_mode_reads_the_month_and_adds_the_column_to_an_old_table(monthly) -> None:
    """Uma tabela criada antes do controle por mês ganha `competencia_envio`; as linhas antigas ficam."""
    service, context_service, url = monthly
    context = service.resolve_context("metas")
    context_service.update(context.id, period_mode=PeriodMode.NONE)
    old_csv = pd.DataFrame({"Data": ["05/09/2026"], "meta": [1]}).to_csv(index=False).encode()
    legacy = service.process_upload(old_csv, "antigo.csv", "metas", "maria")
    assert "competencia_envio" not in _table(url).columns

    context_service.update(
        context.id, period_mode=PeriodMode.MONTHLY, period_source=PeriodSource.COLUMN, period_column="Data"
    )
    csv = pd.DataFrame({"Data": ["05/10/2026", "20/10/2026"], "meta": [7, 8]}).to_csv(index=False).encode()
    history = service.process_upload(csv, "out.csv", "metas", "maria", period="2020-01")

    assert history.period == "2026-10"
    assert history.load_status == LoadStatus.SUCCESS, history.load_error
    table = _table(url)
    assert set(table["id_envio"]) == {legacy.id, history.id}
    assert table.loc[table["id_envio"] == legacy.id, "competencia_envio"].isna().all()
    parquet = pd.read_parquet(history.destination_detail)
    assert "competencia_envio" in parquet.columns
    assert service.resolve_context("metas").expected_columns == "Data,meta"


def test_file_with_reserved_column_name_is_rejected(monthly) -> None:
    service, _, _ = monthly
    csv = pd.DataFrame({"competencia_envio": ["x"], "meta": [1]}).to_csv(index=False).encode()
    history = service.process_upload(csv, "out.csv", "metas", "maria", period="2026-10")
    assert history.status == UploadStatus.ERROR
    assert "nome reservado" in history.error_message


# ── API ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client(tmp_path, monkeypatch):
    main_module = _reset_app_state(tmp_path, monkeypatch)
    with TestClient(main_module.app) as test_client:
        yield test_client
    _reset_app_state(tmp_path, monkeypatch)


def _create_monthly_context(client: TestClient, tmp_path: Path, **fields: object) -> int:
    payload = {
        "name": "metas",
        "destination_type": "local",
        "local_path": str(tmp_path / "metas_dest"),
        "allowed_file_types": "csv",
        "period_mode": "monthly",
        "period_source": "selector",
        **fields,
    }
    response = client.post("/api/contexts", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _send(client: TestClient, period: str | None, **flags: str):
    data = {"context_name": "metas", **flags}
    if period:
        data["period"] = period
    return client.post("/api/uploads", data=data, files={"file": ("metas.csv", b"vendedor,meta\nA,1\n", "text/csv")})


def test_context_api_validates_period_fields(client: TestClient, tmp_path) -> None:
    _login(client, "admin", "admin123")
    response = client.post(
        "/api/contexts",
        json={"name": "metas", "destination_type": "local", "period_mode": "monthly", "period_source": "column"},
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "period_column"

    response = client.post(
        "/api/contexts",
        json={"name": "metas", "destination_type": "local", "period_start": "2026/01"},
    )
    assert response.status_code == 422

    context_id = _create_monthly_context(client, tmp_path, period_start="2026-01", duplicate_policy="block")
    saved = client.get(f"/api/contexts/{context_id}").json()
    assert (saved["period_mode"], saved["period_start"], saved["duplicate_policy"]) == ("monthly", "2026-01", "block")


def test_interactive_upload_asks_before_replacing_a_month(client: TestClient, tmp_path) -> None:
    _login(client, "admin", "admin123")
    _create_monthly_context(client, tmp_path)

    missing = _send(client, None)
    assert missing.status_code == 422
    assert missing.json()["detail"]["kind"] == "period_error"

    assert _send(client, "2026-10").json()["period"] == "2026-10"
    conflict = _send(client, "2026-10")
    assert conflict.status_code == 409
    detail = conflict.json()["detail"]
    assert (detail["kind"], detail["period_label"], detail["uploaded_by"]) == ("period_exists", "outubro/2026", "admin")

    replaced = _send(client, "2026-10", confirm_replace_period="true")
    assert replaced.status_code == 200
    history = client.get("/api/audit?period=2026-10").json()
    assert [item["superseded_by"] for item in history] == [None, replaced.json()["id"]]


def test_api_upload_needs_replace_flag_for_a_sent_month(client: TestClient, tmp_path) -> None:
    _login(client, "admin", "admin123")
    _create_monthly_context(client, tmp_path)
    files = {"file": ("metas.csv", b"vendedor,meta\nA,1\n", "text/csv")}
    assert client.post("/api/upload", data={"context_name": "metas", "period": "2026-10"}, files=files).status_code == 200

    conflict = client.post("/api/upload", data={"context_name": "metas", "period": "2026-10"}, files=files)
    replaced = client.post(
        "/api/upload", data={"context_name": "metas", "period": "2026-10", "replace_period": "true"}, files=files
    )

    assert conflict.status_code == 409
    assert replaced.status_code == 200 and replaced.json()["status"] == "success"


def test_period_grid_is_shared_with_users_of_the_context_only(client: TestClient, tmp_path) -> None:
    _login(client, "admin", "admin123")
    context_id = _create_monthly_context(client, tmp_path, period_start="2026-01")
    _send(client, "2026-02")
    maria_id = _create_user(client, "maria", "senhaforte123")
    _create_user(client, "joao", "senhaforte123")
    client.put(f"/api/users/{maria_id}/contexts", json={"context_ids": [context_id]})

    with TestClient(client.app) as maria:
        _login(maria, "maria", "senhaforte123")
        grid = maria.get("/api/uploads/periods", params={"context_name": "metas", "year": 2026})
        assert grid.status_code == 200
        february = grid.json()["months"][1]
        assert february["state"] == "sent"
        assert february["uploads"][0]["uploaded_by"] == "admin"
        assert grid.json()["months"][0]["state"] == "missing"
        accessible = maria.get("/api/contexts/me/accessible").json()["contexts"][0]
        assert (accessible["period_mode"], accessible["period_source"]) == ("monthly", "selector")

    with TestClient(client.app) as joao:
        _login(joao, "joao", "senhaforte123")
        assert joao.get("/api/uploads/periods", params={"context_name": "metas", "year": 2026}).status_code == 404


def test_bootstrap_adds_period_columns_to_an_old_database(session_factory: DatabaseSessionFactory) -> None:
    """Bancos de antes do controle por mês ganham as colunas novas como nulas."""
    with session_factory.engine.begin() as connection:
        connection.execute(text('ALTER TABLE "upload_history" DROP COLUMN "superseded_by"'))
    from input_arquivos.backend.db.bootstrap import DatabaseBootstrapper

    DatabaseBootstrapper(session_factory, auth_service=None)._sync_missing_columns()
    with session_factory.engine.connect() as connection:
        columns = {row[1] for row in connection.execute(text('PRAGMA table_info("upload_history")'))}
    assert "superseded_by" in columns
