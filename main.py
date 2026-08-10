"""
Entrypoint principal do Sistema de Ingestão de Arquivos (input_arquivos).
Re-exporta a aplicação FastAPI de input_arquivos.main para padronização de inicialização.
"""
from input_arquivos.main import app

__all__ = ["app"]
