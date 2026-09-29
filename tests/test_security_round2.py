"""Testes de regressão da 2ª rodada da revisão de segurança (2026-09-29).

Um teste por achado: upload em contexto sem acesso, contador de lockout sob
concorrência, tempo de login igual com ou sem usuário, sessão revogada em
logout/troca de senha, detalhes internos escondidos do usuário comum, zip
bomb em planilha, CSP nas páginas e SQLite em WAL. O XSS (nomes de coluna)
é corrigido no front-end; aqui fica o teste de que o `esc()` escapa aspas.
"""

import io
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from input_arquivos.backend.config import get_settings
from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.ingestion import readers
from input_arquivos.backend.ingestion.readers import ExcelReader, UploadTooLargeError
from input_arquivos.backend.models.user import User, UserRole
from input_arquivos.backend.services.auth_service import AuthService
from tests.test_security_regressions import _create_user, _login, _reset_app_state


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Cliente HTTP contra um SQLite temporário, com o admin de bootstrap (`admin`/`admin123`)."""
    main_module = _reset_app_state(tmp_path, monkeypatch)
    with TestClient(main_module.app) as test_client:
        yield test_client
    _reset_app_state(tmp_path, monkeypatch)


def _create_context(client: TestClient, tmp_path: Path, name: str = "vendas") -> None:
    response = client.post(
        "/api/contexts",
        json={
            "name": name,
            "destination_type": "local",
            "local_path": str(tmp_path / f"{name}_dest"),
            "allowed_file_types": "csv",
        },
    )
    assert response.status_code == 200, response.text


_CSV = {"file": ("vendas.csv", b"produto,valor\nA,1\n", "text/csv")}


# ── Upload em contexto sem acesso (CWE-285) ──────────────────────────────


@pytest.mark.parametrize("path", ["/api/uploads", "/api/upload"])
def test_user_cannot_upload_to_context_without_access(client: TestClient, tmp_path, path: str) -> None:
    """Enviar para um contexto não liberado dá 404 (igual a inexistente) e não grava nada."""
    _login(client, "admin", "admin123")
    _create_context(client, tmp_path)
    _create_user(client, "maria", "senhaforte123")

    with TestClient(client.app) as user_client:
        _login(user_client, "maria", "senhaforte123")
        response = user_client.post(path, data={"context_name": "vendas"}, files=_CSV)
        assert response.status_code == 404
        cancelled = user_client.post(
            "/api/uploads", data={"context_name": "vendas", "cancelled": "true"}, files=_CSV
        )
        assert cancelled.status_code == 404

    assert client.get("/api/audit").json() == []
    assert not (tmp_path / "vendas_dest").exists()


def test_user_can_upload_to_granted_context(client: TestClient, tmp_path) -> None:
    _login(client, "admin", "admin123")
    _create_context(client, tmp_path)
    user_id = _create_user(client, "maria", "senhaforte123")
    context_id = client.get("/api/contexts").json()[0]["id"]
    assert client.put(f"/api/users/{user_id}/contexts", json={"context_ids": [context_id]}).status_code == 204

    with TestClient(client.app) as user_client:
        _login(user_client, "maria", "senhaforte123")
        response = user_client.post("/api/uploads", data={"context_name": "vendas"}, files=_CSV)
        assert response.status_code == 200
        assert response.json()["status"] == "success"


# ── Detalhes internos só para admin (CWE-209) ────────────────────────────


def test_regular_user_does_not_see_server_path(client: TestClient, tmp_path) -> None:
    _login(client, "admin", "admin123")
    _create_context(client, tmp_path)
    user_id = _create_user(client, "maria", "senhaforte123")
    context_id = client.get("/api/contexts").json()[0]["id"]
    client.put(f"/api/users/{user_id}/contexts", json={"context_ids": [context_id]})

    with TestClient(client.app) as user_client:
        _login(user_client, "maria", "senhaforte123")
        user_client.post("/api/uploads", data={"context_name": "vendas"}, files=_CSV)
        detail = user_client.get("/api/uploads/recent").json()[0]["destination_detail"]
        assert detail.endswith(".parquet") and "/" not in detail

    admin_detail = client.get("/api/audit").json()[0]["destination_detail"]
    assert admin_detail.startswith(str(tmp_path))


def test_write_failure_keeps_technical_detail_for_admin_only(client: TestClient, tmp_path) -> None:
    _login(client, "admin", "admin123")
    blocker = tmp_path / "arquivo_no_lugar_da_pasta"
    blocker.write_text("x")
    client.post(
        "/api/contexts",
        json={"name": "vendas", "destination_type": "local", "local_path": str(blocker), "allowed_file_types": "csv"},
    )
    upload = client.post("/api/uploads", data={"context_name": "vendas"}, files=_CSV).json()
    assert upload["status"] == "error"
    assert str(tmp_path) not in upload["error_message"]
    assert str(tmp_path) in client.get("/api/audit").json()[0]["error_detail"]


# ── Sessão revogada em logout e troca de senha (CWE-613) ─────────────────


def test_logout_invalidates_copied_cookie(client: TestClient) -> None:
    _login(client, "admin", "admin123")
    stolen = client.cookies.get("session")
    assert client.post("/api/auth/logout").status_code == 204

    with TestClient(client.app, cookies={"session": stolen}) as attacker:
        assert attacker.get("/api/auth/me").status_code == 401


def test_password_change_kills_other_sessions_but_keeps_own(client: TestClient) -> None:
    _login(client, "admin", "admin123")
    _create_user(client, "maria", "senhaforte123")

    with TestClient(client.app) as other_device, TestClient(client.app) as own:
        _login(other_device, "maria", "senhaforte123")
        _login(own, "maria", "senhaforte123")
        response = own.post(
            "/api/auth/change-password",
            json={"username": "maria", "current_password": "senhaforte123", "new_password": "outrasenha456"},
        )
        assert response.status_code == 204
        assert own.get("/api/auth/me").status_code == 200
        assert other_device.get("/api/auth/me").status_code == 401


def test_admin_reset_of_other_user_kills_their_session(client: TestClient) -> None:
    _login(client, "admin", "admin123")
    user_id = _create_user(client, "maria", "senhaforte123")

    with TestClient(client.app) as user_client:
        _login(user_client, "maria", "senhaforte123")
        assert client.patch(f"/api/users/{user_id}", json={"new_password": "novasenha789"}).status_code == 200
        assert user_client.get("/api/auth/me").status_code == 401

    # O admin redefinindo a própria senha continua logado.
    admin_id = next(u["id"] for u in client.get("/api/users").json() if u["username"] == "admin")
    assert client.patch(f"/api/users/{admin_id}", json={"new_password": "admin-nova-123"}).status_code == 200
    assert client.get("/api/auth/me").status_code == 200


# ── Lockout sob concorrência (CWE-362) e tempo de login (CWE-208) ─────────


@pytest.fixture
def auth_service(session_factory: DatabaseSessionFactory) -> AuthService:
    service = AuthService(session_factory)
    with session_factory.session() as db_session:
        db_session.add(
            User(username="alvo", password_hash=service.hash_password("certa123"), role=UserRole.USER, active=True)
        )
    return service


def test_parallel_burst_checks_at_most_max_passwords(auth_service: AuthService, session_factory, monkeypatch) -> None:
    """Antes, 40 tentativas em paralelo testavam 40 senhas e a conta nem bloqueava (contador em ~3)."""
    checked = []
    original = auth_service._crypt_context.verify

    def spy(password, hashed):
        if hashed != auth_service._dummy_hash:
            checked.append(password)
        return original(password, hashed)

    monkeypatch.setattr(auth_service._crypt_context, "verify", spy)

    def attempt(i: int) -> None:
        try:
            auth_service.authenticate("alvo", f"errada{i}")
        except ValueError:  # AccountLockedError
            pass

    with ThreadPoolExecutor(20) as pool:
        list(pool.map(attempt, range(20)))

    assert len(checked) <= get_settings().max_failed_login_attempts
    with session_factory.session() as db_session:
        assert db_session.query(User).filter_by(username="alvo").one().locked_until is not None


def test_unknown_user_still_runs_password_hash(auth_service: AuthService, monkeypatch) -> None:
    """Usuário inexistente também passa pelo bcrypt, senão responde bem mais rápido (enumeração)."""
    calls = []
    original = auth_service._crypt_context.verify
    monkeypatch.setattr(auth_service._crypt_context, "verify", lambda *a, **k: calls.append(1) or original(*a, **k))

    assert auth_service.authenticate("nao-existe", "qualquer") is None
    assert calls == [1]


# ── Zip bomb em planilha (CWE-409) ───────────────────────────────────────


def test_spreadsheet_that_expands_too_much_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(readers, "MAX_UNCOMPRESSED_BYTES", 1024 * 1024)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"0" * (2 * 1024 * 1024))
    assert len(buffer.getvalue()) < 64 * 1024  # poucos KB compactado

    with pytest.raises(UploadTooLargeError, match="descompactada"):
        ExcelReader().read(buffer.getvalue())


# ── CSP nas páginas e nenhum handler inline (XSS, CWE-79) ────────────────


def test_pages_send_csp_without_inline_scripts(client: TestClient) -> None:
    csp = client.get("/login").headers["content-security-policy"]
    assert "script-src 'self'" in csp and "'unsafe-inline'" not in csp.split("script-src")[1].split(";")[0]
    assert "frame-ancestors 'none'" in csp


def test_templates_have_no_inline_event_handlers() -> None:
    """O CSP bloqueia onclick="" e afins: as ações ficam em data-click (common.js)."""
    templates = Path("input_arquivos/frontend/templates")
    offenders = [
        f"{path}: {match.group(0)}"
        for path in templates.rglob("*.html")
        for match in re.finditer(r"\son[a-z]+=\"", path.read_text(encoding="utf-8"))
    ]
    assert offenders == []


def test_esc_escapes_quotes_for_attributes() -> None:
    """`esc()` é usado dentro de atributos (value="..."), então precisa escapar aspas."""
    common = Path("input_arquivos/frontend/static/js/common.js").read_text(encoding="utf-8")
    body = common[common.index("function esc(") :].split("}", 1)[0]
    for entity in ("&amp;", "&lt;", "&gt;", "&quot;", "&#039;"):
        assert entity in body


# ── SQLite pronto para acessos simultâneos ───────────────────────────────


def test_sqlite_uses_wal_and_busy_timeout(session_factory: DatabaseSessionFactory) -> None:
    with session_factory.engine.connect() as connection:
        assert connection.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert connection.execute(text("PRAGMA busy_timeout")).scalar() >= 5000
