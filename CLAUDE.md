# CLAUDE.md — Contexto e Diretrizes do Ingestão de Arquivos (`input_arquivos`)

## Visão Geral do Projeto
O **Sistema de Ingestão de Arquivos (`input_arquivos`)** é a solução de upload e pipeline de ingestão de dados em múltiplos formatos (**Excel, CSV, PDF, Imagens/OCR, JSON, XML, TXT, YAML, ODS, HTML**) com conversão automática para **Parquet** e gravação em **MinIO** (ou pasta local, só para testes). Contextos com "Carregar no banco" também inserem o Parquet numa tabela do **SQL Server** (`backend/loaders/database_loader.py`) — como etapa *posterior* ao MinIO, nunca no lugar dele: uma falha no banco não desfaz o upload e pode ser recarregada pelo audit log.

---

## 🛠️ Comandos de Execução Padronizados

```bash
# Entrar no diretório do projeto
cd /home/swordpower/Documentos/REPO/PESSOAL/input_arquivos

# Executar via uv run (Padrão Universal)
uv run uvicorn main:app --reload --port 8004

# Alternativa nomeada
uv run uvicorn input_arquivos.main:app --reload --port 8004

# Executar a Suíte Completa de Testes Automatizados (Pytest)
uv run pytest -v

# Console script: sobe o servidor (input_arquivos/cli.py)
uv run input-arquivos

# Gera uma chave para CONFIG_ENCRYPTION_KEY (só imprime; não sobe o app nem cria arquivo)
uv run input-arquivos gerar-chave
```

- **URL Web Local**: `http://127.0.0.1:8004`

---

## 📐 Arquitetura & Ingestão

- **Pipeline de Conversão**: Excel/CSV/JSON/XML/PDF/Imagem -> Pandas -> PyArrow Parquet -> MinIO (ou pasta local) -> (opcional, por contexto) tabela no SQL Server.
- **Validação de Colunas**: Checagem dinâmica de tipos (Texto, Inteiro, Decimal, Data DD/MM/AAAA, Boolean) e obrigatoriedade.
- **Carga no banco**: 1 contexto = 1 tabela (padrão: slug do nome, igual à pasta no MinIO), coluna `id_envio` = `UploadHistory.id`, modo `append` (idempotente por `id_envio`) ou `replace` (`DELETE` + insert). Situação em `UploadHistory.load_status`; recarga em `POST /api/audit/{id}/load`.
- **Área Administrativa (`/admin`)**: Gestão de Contextos de negócio, Usuários, configuração do MinIO e do SQL Server de destino (`/admin/settings`, credenciais cifradas em repouso; servidor/porta/banco/usuário/senha em campos separados — a URL é montada no backend com `URL.create`, driver fixo `mssql+pymssql`) e Log de Auditoria.

## Diferenças em relação ao padrão do app_template

Este é o app mais divergente do ecossistema — de propósito, não por drift: multiusuário real com sessão/cookie assinado (`itsdangerous`), auth com bcrypt + lockout de tentativas (`backend/services/auth_service.py` — mais completo que o `auth_service.py` do `app_template`, candidato a backport), ORM SQLAlchemy 2.0 síncrono sobre SQLite, MPA Jinja2 com herança real de template (`base.html`). Não tem crypto_vault/KV-store/task_runner/log_buffer do template — o domínio não usa nada disso (rastreabilidade é via `UploadHistory`/`/api/audit`, não um buffer de log em memória).

- **`backend/api/routes_system.py`** (novo): `GET /api/system/health`, `/metrics` — únicos endpoints de paridade adicionados, protegidos por `require_admin` (mesmo padrão de `/api/audit`). Sem `/logs`: projeto não usa o módulo `logging` do Python em lugar nenhum.
- **Tema**: `frontend/static/css/theme.css` agora tem os 3 temas (`corporate`/`green-neutral`/`cyber-dark`), completando o que faltava.
- **`cli.py`**: o console script `input-arquivos` aponta para `input_arquivos.cli:main` (subcomandos `servir`, padrão, e `gerar-chave`). Fica fora de `main.py` porque importar `main` já roda o bootstrap (cria banco e arquivo de chave).
- **Chave de cifra**: `CONFIG_ENCRYPTION_KEY` (env) tem prioridade; sem ela, `data/.config_encryption_key` (gerado automaticamente). Ver `backend/security/secret_box.py`.

## Revisão de Segurança

@~/.claude/security-review-checklist.md
