"""Schemas Pydantic para a rota de configuração global do MinIO (`/admin/settings`)."""

from pydantic import BaseModel


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
