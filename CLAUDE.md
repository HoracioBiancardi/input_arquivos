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

# Executar a Suíte Completa de Testes Automatizados (Pytest - 87 testes)
uv run pytest -v

# Console script (agora funcional — antes o entry point `start` não existia)
uv run input-arquivos
```

- **URL Web Local**: `http://127.0.0.1:8004`

---

## 📐 Arquitetura & Ingestão

- **Pipeline de Conversão**: Excel/CSV/JSON/XML/PDF/Imagem -> Pandas -> PyArrow Parquet -> MinIO / SQL Server.
- **Validação de Colunas**: Checagem dinâmica de tipos (Texto, Inteiro, Decimal, Data DD/MM/AAAA, Boolean) e obrigatoriedade.
- **Área Administrativa (`/admin`)**: Gestão de Contextos de negócio, Usuários e Log de Auditoria.

## Diferenças em relação ao padrão do app_template

Este é o app mais divergente do ecossistema — de propósito, não por drift: multiusuário real com sessão/cookie assinado (`itsdangerous`), auth com bcrypt + lockout de tentativas (`backend/services/auth_service.py` — mais completo que o `auth_service.py` do `app_template`, candidato a backport), ORM SQLAlchemy 2.0 síncrono sobre SQLite, MPA Jinja2 com herança real de template (`base.html`). Não tem crypto_vault/KV-store/task_runner/log_buffer do template — o domínio não usa nada disso (rastreabilidade é via `UploadHistory`/`/api/audit`, não um buffer de log em memória).

- **`backend/api/routes_system.py`** (novo): `GET /api/system/health`, `/metrics` — únicos endpoints de paridade adicionados, protegidos por `require_admin` (mesmo padrão de `/api/audit`). Sem `/logs`: projeto não usa o módulo `logging` do Python em lugar nenhum.
- **Tema**: `frontend/static/css/theme.css` agora tem os 3 temas (`corporate`/`green-neutral`/`cyber-dark`), completando o que faltava.
- **`main.py::start()`** (novo): o console script `input-arquivos` declarado em `pyproject.toml` apontava pra uma função que não existia — corrigido.
