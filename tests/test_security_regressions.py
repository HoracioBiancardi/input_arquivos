"""Testes de regressão HTTP para os achados da revisão de segurança do input_arquivos.

Cada teste aqui corresponde a um item da revisão (ver CLAUDE.md/histórico do
projeto): sessão revalidada contra o banco, cookie não forjável com o secret
padrão antigo, admin-gate em rotas sensíveis, IDOR em preview/listagem de
uploads, spoofing de `uploaded_by`, limite de tamanho de upload, `/docs`
fechado por padrão, `must_change_password` no bootstrap e status code
unificado no lockout de login.

Usa o mesmo padrão de fixture de `test_system_routes.py`: recarrega
`input_arquivos.main` contra um SQLite temporário para não tocar no banco de
desenvolvimento real.
"""

import importlib

import pytest
from fastapi.testclient import TestClient
from itsdangerous import URLSafeTimedSerializer


def _reset_app_state(tmp_path, monkeypatch, extra_env: dict[str, str] | None = None):
    """Aponta a app para um SQLite temporário e força o rebuild de settings/container/app.

    Args:
        tmp_path: Diretório temporário do teste.
        monkeypatch: Fixture do pytest para setar variáveis de ambiente.
        extra_env: Variáveis de ambiente adicionais a definir antes do rebuild
            (ex.: `MAX_UPLOAD_SIZE_BYTES` para o teste de limite de upload).

    Returns:
        O módulo `input_arquivos.main` recarregado, com `app` já construído.
    """
    monkeypatch.setenv("APP_CONFIG_DB_PATH", str(tmp_path / "test_security_app_config.db"))
    for key, value in (extra_env or {}).items():
        monkeypatch.setenv(key, value)

    from input_arquivos.backend import config as config_module
    from input_arquivos.backend.db import session as session_module
    from input_arquivos.backend.services import container as container_module

    config_module.get_settings.cache_clear()
    session_module._factory = None
    container_module._container = None

    import input_arquivos.main as main_module

    importlib.reload(main_module)
    return main_module


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Cliente de teste com um admin previsível (`admin`/`admin123`, defaults de bootstrap)."""
    main_module = _reset_app_state(tmp_path, monkeypatch)
    with TestClient(main_module.app) as test_client:
        yield test_client

    from input_arquivos.backend import config as config_module
    from input_arquivos.backend.db import session as session_module
    from input_arquivos.backend.services import container as container_module

    config_module.get_settings.cache_clear()
    session_module._factory = None
    container_module._container = None


def _login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text


def _create_user(client: TestClient, username: str, password: str, role: str = "user") -> int:
    response = client.post("/api/users", json={"username": username, "password": password, "role": role})
    assert response.status_code == 200, response.text
    return response.json()["id"]


# ── #11: /docs fechado por padrão ────────────────────────────────────────


def test_docs_disabled_by_default(client: TestClient) -> None:
    """`/docs`, `/redoc` e `/openapi.json` não devem existir sem `DEBUG=true`."""
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


# ── #1: sessão revalidada contra o banco + cookie não forjável ──────────


@pytest.mark.parametrize(
    "path", ["/api/auth/me", "/api/contexts", "/api/users", "/api/audit", "/api/uploads/recent"]
)
def test_protected_routes_require_login(client: TestClient, path: str) -> None:
    """Nenhuma rota protegida deve responder sem uma sessão válida."""
    assert client.get(path).status_code == 401


def test_garbage_cookie_is_rejected(client: TestClient) -> None:
    """Um cookie de sessão corrompido/inventado deve ser tratado como sessão ausente."""
    client.cookies.set("session", "garbage.invalid.token")
    assert client.get("/api/auth/me").status_code == 401


def test_cookie_forged_with_old_known_default_secret_is_rejected(client: TestClient) -> None:
    """Um cookie assinado com o antigo secret padrão ("change-me-in-production") não deve autenticar.

    Esse era o vetor do achado crítico: como o secret padrão era conhecido
    (está no código-fonte), qualquer um conseguia forjar offline um cookie
    `role=admin` válido. A correção gera um secret aleatório real na
    primeira execução — então um token assinado com o valor antigo falha na
    verificação de assinatura.
    """
    serializer = URLSafeTimedSerializer("change-me-in-production", salt="session-cookie")
    forged_token = serializer.dumps({"user_id": 1, "username": "admin", "role": "admin"})

    client.cookies.set("session", forged_token)
    assert client.get("/api/auth/me").status_code == 401


def test_deactivated_user_loses_access_immediately(client: TestClient) -> None:
    """Desativar uma conta deve invalidar a sessão dela na próxima requisição, sem esperar o cookie expirar.

    Antes da correção, `role`/dados do usuário vinham só do cookie assinado
    e não eram checados contra o banco — uma conta desativada continuava
    "logada" até o cookie expirar (até 12h por padrão).
    """
    _login(client, "admin", "admin123")
    user_id = _create_user(client, "joao", "senhaforte123")

    with TestClient(client.app) as user_client:
        _login(user_client, "joao", "senhaforte123")
        assert user_client.get("/api/auth/me").status_code == 200

        deactivate = client.patch(f"/api/users/{user_id}", json={"active": False})
        assert deactivate.status_code == 200

        assert user_client.get("/api/auth/me").status_code == 401


# ── #4: db_connection_string só para admin ───────────────────────────────


def test_regular_user_cannot_list_contexts(client: TestClient) -> None:
    """`GET /api/contexts` (que inclui `db_connection_string`) deve ser admin-only."""
    _login(client, "admin", "admin123")
    _create_user(client, "maria", "senhaforte123")

    with TestClient(client.app) as user_client:
        _login(user_client, "maria", "senhaforte123")
        assert user_client.get("/api/contexts").status_code == 403
        assert user_client.post(
            "/api/contexts",
            json={
                "name": "hack",
                "destination_type": "local",
                "local_path": "/tmp/hack",
                "allowed_file_types": "csv",
            },
        ).status_code == 403

    # Usuário comum continua acessando a listagem restrita, sem dados sensíveis.
    with TestClient(client.app) as user_client:
        _login(user_client, "maria", "senhaforte123")
        accessible = user_client.get("/api/contexts/me/accessible")
        assert accessible.status_code == 200


def test_regular_user_cannot_self_promote(client: TestClient) -> None:
    """Um usuário comum não pode alterar o próprio papel para admin."""
    _login(client, "admin", "admin123")
    user_id = _create_user(client, "maria", "senhaforte123")

    with TestClient(client.app) as user_client:
        _login(user_client, "maria", "senhaforte123")
        response = user_client.patch(f"/api/users/{user_id}", json={"role": "admin"})
        assert response.status_code == 403


# ── #5: IDOR em preview/listagem de uploads ──────────────────────────────


def test_user_without_context_access_cannot_preview_or_list_others_uploads(
    client: TestClient, tmp_path
) -> None:
    """Um usuário sem acesso ao context de um upload não deve enxergá-lo (preview nem listagem)."""
    _login(client, "admin", "admin123")
    _create_user(client, "maria", "senhaforte123")

    context_response = client.post(
        "/api/contexts",
        json={
            "name": "vendas",
            "destination_type": "local",
            "local_path": str(tmp_path / "vendas_dest"),
            "allowed_file_types": "csv",
        },
    )
    assert context_response.status_code == 200

    upload_response = client.post(
        "/api/uploads",
        data={"context_name": "vendas"},
        files={"file": ("vendas.csv", b"produto,valor\nA,1\n", "text/csv")},
    )
    assert upload_response.status_code == 200
    upload_id = upload_response.json()["id"]

    with TestClient(client.app) as user_client:
        _login(user_client, "maria", "senhaforte123")

        preview = user_client.get(f"/api/uploads/{upload_id}/preview")
        assert preview.status_code == 404

        recent = user_client.get("/api/uploads/recent")
        assert recent.status_code == 200
        assert recent.json() == []

    # O próprio admin continua enxergando normalmente.
    own_preview = client.get(f"/api/uploads/{upload_id}/preview")
    assert own_preview.status_code == 200


# ── #9: uploaded_by não pode ser forjado ─────────────────────────────────


def test_uploaded_by_comes_from_session_not_form_field(client: TestClient, tmp_path) -> None:
    """`/api/upload` (headless) deve gravar `uploaded_by` como o usuário da sessão, não um valor arbitrário do form."""
    _login(client, "admin", "admin123")
    client.post(
        "/api/contexts",
        json={
            "name": "vendas",
            "destination_type": "local",
            "local_path": str(tmp_path / "vendas_dest"),
            "allowed_file_types": "csv",
        },
    )

    response = client.post(
        "/api/upload",
        data={"context_name": "vendas", "uploaded_by": "outra-pessoa"},
        files={"file": ("vendas.csv", b"produto,valor\nA,1\n", "text/csv")},
    )
    assert response.status_code == 200
    assert response.json()["uploaded_by"] == "admin"


# ── #8: limite de tamanho de upload ──────────────────────────────────────


def test_oversized_upload_is_rejected(tmp_path, monkeypatch) -> None:
    """Um upload maior que `MAX_UPLOAD_SIZE_BYTES` deve ser rejeitado com 413 antes de ser lido."""
    main_module = _reset_app_state(tmp_path, monkeypatch, extra_env={"MAX_UPLOAD_SIZE_BYTES": "1024"})
    with TestClient(main_module.app) as test_client:
        _login(test_client, "admin", "admin123")
        test_client.post(
            "/api/contexts",
            json={
                "name": "vendas",
                "destination_type": "local",
                "local_path": str(tmp_path / "vendas_dest"),
                "allowed_file_types": "csv",
            },
        )

        response = test_client.post(
            "/api/uploads",
            data={"context_name": "vendas"},
            files={"file": ("grande.csv", b"x" * 5000, "text/csv")},
        )
        assert response.status_code == 413


# ── #10: must_change_password no bootstrap ───────────────────────────────


def test_bootstrap_admin_is_flagged_to_change_password(client: TestClient) -> None:
    """O admin criado pelo bootstrap deve nascer com `must_change_password=True`."""
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    assert response.json()["must_change_password"] is True

    me = client.get("/api/auth/me")
    assert me.json()["must_change_password"] is True


def test_must_change_password_clears_after_password_reset(client: TestClient) -> None:
    """Redefinir a senha do admin deve zerar `must_change_password`."""
    _login(client, "admin", "admin123")
    users = client.get("/api/users").json()
    admin_id = next(user["id"] for user in users if user["username"] == "admin")

    reset = client.patch(f"/api/users/{admin_id}", json={"new_password": "novaSenhaForte123"})
    assert reset.status_code == 200

    with TestClient(client.app) as fresh_client:
        login_response = fresh_client.post(
            "/api/auth/login", json={"username": "admin", "password": "novaSenhaForte123"}
        )
        assert login_response.status_code == 200
        assert login_response.json()["must_change_password"] is False


# ── #12: status code unificado no lockout de login ───────────────────────


def test_locked_account_returns_same_status_as_invalid_credentials(client: TestClient) -> None:
    """Conta bloqueada por tentativas erradas deve responder 401 (mesmo status de credencial inválida).

    Antes da correção, bloqueio devolvia 423 e credencial inválida devolvia
    401 — um atacante conseguia enumerar usernames válidos só observando
    qual username eventualmente resulta em 423 depois de várias tentativas.
    """
    _login(client, "admin", "admin123")
    _create_user(client, "bloqueavel", "senhaforte123")

    invalid_response = None
    for _ in range(6):
        invalid_response = client.post(
            "/api/auth/login", json={"username": "bloqueavel", "password": "senha-errada"}
        )

    assert invalid_response.status_code == 401
    assert "bloqueada" in invalid_response.json()["detail"].lower()

    unknown_user_response = client.post(
        "/api/auth/login", json={"username": "usuario-que-nao-existe", "password": "qualquer"}
    )
    assert unknown_user_response.status_code == invalid_response.status_code == 401
