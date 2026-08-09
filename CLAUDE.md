# CLAUDE.md — Contexto e Diretrizes do Ingestão de Arquivos (`input_arquivos`)

## Visão Geral do Projeto
O **Sistema de Ingestão de Arquivos (`input_arquivos`)** é a solução de upload e pipeline de ingestão de dados em múltiplos formatos (**Excel, CSV, PDF, Imagens/OCR, JSON, XML, TXT, YAML, ODS, HTML**) com conversão automática para **Parquet** e gravação em **MinIO** ou **SQL Server**.

---

## 🛠️ Comandos de Execução Padronizados

```bash
# Entrar no diretório do projeto
cd /home/swordpower/Documentos/REPO/PESSOAL/input_arquivos

# Executar via uv run (Padrão Universal)
uv run uvicorn main:app --reload --port 8004

# Alternativa nomeada
uv run uvicorn input_arquivos.main:app --reload --port 8004

# Executar a Suíte Completa de Testes Automatizados (Pytest - 85 testes)
uv run pytest -v
```

- **URL Web Local**: `http://127.0.0.1:8004`

---

## 📐 Arquitetura & Ingestão

- **Pipeline de Conversão**: Excel/CSV/JSON/XML/PDF/Imagem -> Pandas -> PyArrow Parquet -> MinIO / SQL Server.
- **Validação de Colunas**: Checagem dinâmica de tipos (Texto, Inteiro, Decimal, Data DD/MM/AAAA, Boolean) e obrigatoriedade.
- **Área Administrativa (`/admin`)**: Gestão de Contextos de negócio, Usuários e Log de Auditoria.
