# Sistema de Ingestão de Arquivos

Upload de arquivos (Excel, CSV, PDF) com conversão automática para **Parquet** e envio para
**MinIO** (bucket) ou **SQL Server** (tabela), de acordo com um **contexto de negócio** (ex.:
"vendas"). Cada envio grava `data_envio`, `contexto` e `enviado_por` como as três primeiras colunas
do resultado. Uma área administrativa (`/admin`, protegida por login) gerencia os contexts, os
usuários do sistema e o audit log de uploads.

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) como gerenciador de pacotes
- Um servidor **MinIO** acessível (para contexts do tipo MinIO)
- Um servidor **SQL Server** acessível (para contexts do tipo SQL Server)
- **Driver ODBC 17 ou 18 da Microsoft** instalado no sistema operacional — é a única dependência
  não-Python do projeto, exigida pelo `pyodbc` para conectar no SQL Server. No Linux (Debian/Ubuntu),
  siga o guia oficial da Microsoft para instalar `msodbcsql18` + `unixodbc`.

## Instalação

```bash
uv sync
cp .env.example .env
# edite o .env: STORAGE_SECRET, credenciais do admin bootstrap e do MinIO
```

## Executar

```bash
uv run uvicorn app.main:app --reload
```

A aplicação sobe em `http://localhost:8080` (porta configurável via `.env`):

- `/login` — login (obrigatório para qualquer usuário)
- `/` — tela de upload de arquivos
- `/admin` — área administrativa (contexts, usuários, audit log) — apenas para usuários com papel `admin`
- `/docs` — documentação interativa da API REST (`/api/*`)

No primeiro start, um usuário admin é criado automaticamente a partir de `ADMIN_BOOTSTRAP_USERNAME`
e `ADMIN_BOOTSTRAP_PASSWORD` (definidos no `.env`). Troque a senha (ou crie novos usuários) pela
tela `/admin/users` assim que possível.

## Testes

```bash
uv run pytest
uv run ruff check .
```

Os testes cobrem o pipeline de ingestão (Excel/CSV), a conversão Parquet, o CRUD de contexts e a
lógica de append/create-versionado do writer de SQL Server (esta última validada contra um SQLite
temporário, já que a lógica de branching é agnóstica de dialeto SQL — particularidades reais do
SQL Server/`pyodbc` devem ser conferidas manualmente, ver seção abaixo).

## Testando sem MinIO/SQL Server (destino "Pasta local")

Além de MinIO e SQL Server, um context pode usar `destination_type = local`: em vez de subir para
um bucket ou banco externo, o Parquet (ou o PDF bruto, em modo raw_archive) é salvo direto numa
pasta no disco, com a mesma estrutura de particionamento por data usada no MinIO
(`{pasta_raiz}/{contexto}/{ano}/{mes}/{dia}/arquivo_HHMMSS_uuid.parquet`). Em `/admin/contexts`,
escolha "Pasta local" como destino e informe uma pasta raiz (ex.: `data/local_storage`) — o nome
do contexto já vira subpasta automaticamente, então a mesma raiz pode ser reaproveitada por vários
contexts. Use o botão "Testar/criar pasta local" para confirmar que a pasta é gravável. Isso permite
testar o fluxo completo (upload → conversão → persistência com `data_envio`/`contexto`/`enviado_por`)
sem nenhuma conexão externa.

## Verificação manual ponta a ponta

Sem MinIO/SQL Server disponíveis, é possível validar toda a lógica de negócio localmente (testes
automatizados acima, ou usando um context do tipo "Pasta local" descrito na seção anterior). Para
validar a integração real com MinIO/SQL Server:

1. Suba instâncias descartáveis para teste (não fazem parte da infraestrutura do projeto):
   ```bash
   docker run -p 9000:9000 -p 9001:9001 minio/minio server /data --console-address ":9001"
   docker run -e "ACCEPT_EULA=Y" -e "MSSQL_SA_PASSWORD=SuaSenhaForte123" -p 1433:1433 mcr.microsoft.com/mssql/server
   ```
2. Em `/admin/contexts`, crie um context de cada tipo (MinIO e SQL Server) e use os botões
   "Testar conexão" para confirmar que os dados de conexão estão corretos.
3. Em `/admin/users`, crie um usuário comum (não-admin).
4. Faça login como esse usuário comum em `/` e envie um Excel/CSV/PDF para cada context.
5. Confira: o objeto no console do MinIO / as linhas na tabela do SQL Server (com
   `data_envio`/`contexto`/`enviado_por` corretos) e o registro correspondente em `/admin/audit`.
6. Teste um caso de erro proposital (ex.: append com colunas incompatíveis) e confirme que o
   audit log mostra uma mensagem de erro clara, sem stack trace vazando para a UI.
7. Confirme que o usuário comum não consegue acessar `/admin` diretamente pela URL.

## Estrutura de pastas

```
app/
├── main.py              # cria o FastAPI, inclui a API e monta a UI NiceGUI
├── config.py            # configurações (variáveis de ambiente/.env)
├── db/                  # engine/sessão SQLAlchemy + bootstrap do banco local
├── models/               # modelos ORM: Context, UploadHistory, User
├── schemas/              # schemas Pydantic da API REST
├── ingestion/            # leitores de arquivo, conversão Parquet e orquestração do pipeline
├── destinations/         # writers de destino (MinIO, SQL Server) + registry
├── services/             # camada de serviços (contexts, usuários, upload, auth) + container de DI
├── api/                  # rotas REST (/api/contexts, /api/upload, /api/audit)
├── auth/                 # guard de autenticação das páginas NiceGUI
└── ui/
    ├── pages/             # login e upload (uso geral)
    └── admin/             # dashboard, contexts, usuários e audit log (admin)
tests/                    # testes automatizados (pytest)
data/                     # SQLite local de configuração (gitignored)
```

## Notas de arquitetura

- **MinIO**: endpoint e credenciais são globais (`.env`), compartilhados por todos os contexts —
  cada context define apenas o bucket a usar nesse mesmo servidor.
- **SQL Server**: cada context tem sua própria connection string, podendo apontar para bancos ou
  servidores diferentes.
- **Autenticação**: usa a sessão nativa do NiceGUI (`app.storage.user`, cookie assinado por
  `STORAGE_SECRET`) em vez de JWT — a UI é inteiramente NiceGUI, então isso é mais simples de manter
  com o mesmo nível de segurança. A API REST (`/api/*`) não exige autenticação nesta versão.
