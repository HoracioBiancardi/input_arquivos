"""Schemas Pydantic para as rotas de configuração global do MinIO e do SQL Server de destino (`/admin/settings`)."""

import re

from pydantic import BaseModel, Field, field_validator

_HOST_PATTERN = re.compile(r"^[A-Za-z0-9._-]+(\\[A-Za-z0-9_$-]+)?$")


class MinioConfigResponse(BaseModel):
    """Configuração do MinIO atualmente em uso, segura para retornar pela API.

    Attributes:
        endpoint: Endereço (host:porta) do servidor MinIO.
        access_key: Chave de acesso do MinIO.
        secure: Se a conexão com o MinIO usa HTTPS.
        secret_key_configured: Se há uma chave secreta configurada (nunca
            retornada em texto puro).
        source: De onde vem esta configuração: `"admin"` (salva via
            `/admin/settings`) ou `"env"` (fallback do `.env`).
    """

    endpoint: str
    access_key: str
    secure: bool
    secret_key_configured: bool
    source: str


class MinioConfigUpdateRequest(BaseModel):
    """Corpo da requisição para salvar a configuração do MinIO.

    Attributes:
        endpoint: Endereço (host:porta) do servidor MinIO.
        access_key: Chave de acesso do MinIO.
        secret_key: Chave secreta do MinIO. Deixe em branco para manter a
            chave já salva (só é obrigatória na primeira configuração).
        secure: Se a conexão com o MinIO deve usar HTTPS.
    """

    endpoint: str
    access_key: str
    secret_key: str | None = None
    secure: bool = False


class MinioConfigTestRequest(BaseModel):
    """Corpo da requisição para testar uma configuração de MinIO ainda não salva.

    Attributes:
        endpoint: Endereço (host:porta) do servidor MinIO a testar.
        access_key: Chave de acesso a testar.
        secret_key: Chave secreta a testar.
        secure: Se a conexão deve usar HTTPS.
    """

    endpoint: str
    access_key: str
    secret_key: str
    secure: bool = False


class DatabaseConfigResponse(BaseModel):
    """Conexão do SQL Server de destino da carga de tabelas, segura para retornar pela API.

    Attributes:
        configured: Se há uma conexão completa salva.
        host: Servidor (hostname ou IP).
        port: Porta do SQL Server.
        database: Nome do banco de dados.
        username: Usuário do SQL Server.
        password_configured: Se há uma senha salva (nunca retornada em texto puro).
    """

    configured: bool
    host: str | None
    port: int
    database: str | None
    username: str | None
    password_configured: bool


class DatabaseConfigRequest(BaseModel):
    """Corpo da requisição para salvar ou testar a conexão do SQL Server de destino.

    Cada parte da conexão vem num campo próprio — a URL é montada no
    servidor, então caracteres especiais na senha não quebram nada.

    Attributes:
        host: Servidor (hostname ou IP), sem esquema nem porta.
        port: Porta do SQL Server.
        database: Nome do banco de dados.
        username: Usuário do SQL Server.
        password: Senha. Em branco mantém (ou, no teste, usa) a senha já salva.
    """

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=1433, ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=255)
    password: str | None = None

    @field_validator("host")
    @classmethod
    def _validate_host(cls, value: str) -> str:
        """Aceita só hostname/IP (com `\\instância` opcional), sem esquema, porta ou caminho."""
        stripped = value.strip()
        if not _HOST_PATTERN.match(stripped):
            raise ValueError("Informe só o nome ou IP do servidor (ex.: sql.empresa.local), sem porta nem ://.")
        return stripped

    @field_validator("database", "username")
    @classmethod
    def _strip(cls, value: str) -> str:
        """Remove espaços nas pontas e garante que o campo não ficou vazio."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("Campo obrigatório.")
        return stripped
