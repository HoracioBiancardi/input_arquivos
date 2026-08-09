"""
Entrypoint principal do Sistema de Ingestão de Arquivos (input_arquivos).
Re-exporta a aplicação FastAPI de app.main para padronização de inicialização.
"""
from app.main import app

__all__ = ["app"]
