"""Rotas de health check e métricas operacionais (paridade com o app_template).

Sem `/logs`: este projeto não usa o módulo `logging` do Python em lugar
nenhum — a rastreabilidade persistente já é feita via `UploadHistory` e
`GET /api/audit`. Um buffer de log em memória ficaria vazio sem instrumentar
chamadas de log em vários pontos do código, fora do escopo desta rota.
"""

import time

from fastapi import APIRouter, Depends

from input_arquivos.backend.auth.dependencies import require_admin
from input_arquivos.backend.services.container import get_container

router = APIRouter(prefix="/api/system", tags=["system"], dependencies=[Depends(require_admin)])

_START_TIME = time.time()


@router.get("/health")
def health_check() -> dict:
    """Reporta liveness do processo e uptime."""
    return {"status": "ok", "app": "Sistema de Ingestão de Arquivos", "uptime_seconds": round(time.time() - _START_TIME, 2)}


@router.get("/metrics")
def get_metrics() -> dict:
    """Reporta uptime e contagens não sensíveis (sem dados de usuário/config)."""
    container = get_container()
    return {
        "uptime_seconds": round(time.time() - _START_TIME, 2),
        "total_users": len(container.user_service.list_all()),
        "total_contexts": len(container.context_service.list_all()),
    }
