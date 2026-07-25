"""Configurações da aplicação, carregadas de variáveis de ambiente/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações globais da aplicação.

    Attributes:
        app_config_db_path: Caminho do arquivo SQLite usado para guardar
            contexts, usuários e o histórico de uploads.
        session_secret: Chave usada para assinar o cookie de sessão do login.
        session_max_age_seconds: Tempo de vida (em segundos) do cookie de
            sessão antes de exigir novo login.
        max_failed_login_attempts: Quantidade de tentativas de login com senha
            incorreta permitidas antes de bloquear a conta temporariamente.
        lockout_duration_seconds: Duração (em segundos) do bloqueio de login
            após exceder `max_failed_login_attempts`.
        admin_bootstrap_username: Nome do primeiro usuário admin, criado
            automaticamente se a tabela de usuários estiver vazia.
        admin_bootstrap_password: Senha do primeiro usuário admin.
        minio_endpoint: Endereço (host:porta) do servidor MinIO compartilhado
            por todos os contexts. Cada context aponta apenas para o bucket
            que deve usar nesse mesmo servidor.
        minio_access_key: Chave de acesso do servidor MinIO.
        minio_secret_key: Chave secreta do servidor MinIO.
        minio_secure: Se a conexão com o MinIO deve usar HTTPS.
        host: Endereço de bind do servidor Uvicorn.
        port: Porta de bind do servidor Uvicorn.
        reload: Se o Uvicorn deve recarregar automaticamente em mudanças de código.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_config_db_path: Path = Path("data/app_config.db")
    session_secret: str = "change-me-in-production"
    session_max_age_seconds: int = 12 * 60 * 60
    max_failed_login_attempts: int = 5
    lockout_duration_seconds: int = 15 * 60
    admin_bootstrap_username: str = "admin"
    admin_bootstrap_password: str = "admin123"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_secure: bool = False
    host: str = "0.0.0.0"
    port: int = 8080
    reload: bool = False


@lru_cache
def get_settings() -> Settings:
    """Retorna a instância (cacheada) das configurações da aplicação.

    Returns:
        Instância única de `Settings` carregada a partir do ambiente/.env.
    """
    return Settings()
