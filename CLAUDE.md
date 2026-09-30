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
- **Casca = app_template**: `static/css/style.css` é **cópia exata** do template (o app tem visual único, o da Blau — sem `theme.css`); o domínio e um subconjunto pequeno de utilitários de layout (os nomes que o markup/JS já usavam, antes vindos do Tailwind por CDN — removido) ficam em `static/css/app.css`. `base.html` monta topbar (☰, marca, usuário, online, Sair), activity bar e lateral com links (Envio; e, para admin, Contextos, Usuários, Conexões, Auditoria — `/admin` redireciona para Contextos) marcados pelo `request.url.path`, filtro e largura arrastável (`common.js`), toasts empilhados, ícones Material Symbols e o modal de Ajustes (auto-lock e "Alterar minha senha"). O conteúdo de cada página entra numa `.tab-view` (título `page-title`, `card glass`, `data-table`). Mensagens de acesso (saiu, inatividade, sessão expirada, erro) ficam no card de login (`/login?motivo=`).
- **Design system Blau** (`static/css/blau-tokens.css` + `blau-spa.css` + `static/img/logo-blau.png`): visual único do app, sem troca de tema. Os dois CSS são **cópias** de `app_template/design_system/blau/` (fonte única; não edite aqui, mude lá e copie). Ativado por `<body class="theme-blau">` fixo no `base.html` (tokens e adaptador só valem sob essa classe). O `style.css` não tem cor fixa: tudo vem dos tokens. Tirado do CSS público de blau.com (marinho `#011689`, céu `#36B3E3`, vermelho `#E3010F`, PT Sans). Sobrescreve os tokens e as cores fixas escuras do `style.css` sem editá-lo. O azul-céu tem 2.4:1 sobre branco, então é só decorativo (faixas, foco, item ativo); ações e títulos usam o marinho. O logo (`.brand-logo`) substitui o ícone da casca na topbar e no login.
- **Origem das escritas**: `backend/security/web_guard.py` recusa POST/PUT/PATCH/DELETE em `/api/*` com `Sec-Fetch-Site` de outra origem (outra porta/subdomínio do mesmo domínio passa pelo `SameSite=Strict`) e põe `Content-Security-Policy`, `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy` e `Permissions-Policy` em tudo, mais `no-store` na API. O Caddy só acrescenta HSTS e esconde `Server`.
- **Sem JavaScript inline**: o CSP tem `script-src 'self'`, então `onclick=""`/`onchange=""` nos templates não rodam (e `tests/test_security_round2.py` falha). Ação de botão vai em `data-click="<ação>"` (mapa `CLICK_ACTIONS` em `common.js`; `data-click="call" data-fn="closeX"` chama `window.closeX`), `data-toggle-pw`/`data-gen-pw` para senha, e o resto com `addEventListener` no `.js` da tela.
- **Texto de arquivo é texto de usuário**: nome de coluna, aba, etc. aparecem em telas de admin (regras, aviso de colunas). Nunca interpolar em HTML sem `esc()` — nem em `join(", ")` nem no fallback `LABELS[x] || x`; para `<option>`, criar o elemento e setar `.value`.
- **Sessão revogável**: `User.session_version` vai no cookie (`sv`) e é conferido em toda requisição. Logout e troca de senha incrementam o valor (derruba todas as sessões da conta); quem troca a própria senha logado recebe cookie novo (`SessionCookie.issue_for`).
- **Usuário comum não vê detalhe interno**: `UploadHistoryResponse.redacted()` tira caminho do servidor e erro técnico da carga; falha de gravação no destino guarda o técnico em `UploadHistory.error_detail` (só no `/api/audit`).
- **`cli.py`**: o console script `input-arquivos` aponta para `input_arquivos.cli:main` (subcomandos `servir`, padrão, e `gerar-chave`). Fica fora de `main.py` porque importar `main` já roda o bootstrap (cria banco e arquivo de chave).
- **Chave de cifra**: `CONFIG_ENCRYPTION_KEY` (env) tem prioridade; sem ela, `data/.config_encryption_key` (gerado automaticamente). Ver `backend/security/secret_box.py`.

## Revisão de Segurança

@~/.claude/security-review-checklist.md
