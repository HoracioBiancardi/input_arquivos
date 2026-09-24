# Sistema de Ingestão de Arquivos

Upload de arquivos (Excel, CSV, PDF, imagem, JSON, XML, TXT, YAML, ODS, HTML) com conversão
automática para **Parquet** e envio para
**MinIO** (bucket), de acordo com um **contexto de negócio** (ex.:
"vendas"). Cada envio grava `data_envio`, `contexto` e `enviado_por` como as três primeiras colunas
do resultado. Cada contexto pode ter **regras de validação de dados por coluna** (tipo esperado e
obrigatoriedade), que rejeitam o arquivo inteiro se alguma célula estiver fora do esperado — ver
seção [Validação de dados por coluna](#validação-de-dados-por-coluna) abaixo. Contextos marcados
com "Carregar no banco" também viram uma **tabela no SQL Server** — ver
[Carga em tabela no banco](#carga-em-tabela-no-banco-sql-server). Uma área administrativa
(`/admin`, protegida por login) gerencia os contexts, os usuários do sistema, a configuração do MinIO
e do banco de destino, e o audit log de uploads.

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) como gerenciador de pacotes
- Um servidor **MinIO** acessível (para contexts do tipo MinIO)

O OCR local usado para extrair tabelas de imagens (contexts com `image_mode` diferente de
`raw_archive`) é feito com `RapidOCR` (via `img2table[rapidocr]`), um motor 100% Python/ONNX — não
exige nenhum binário de sistema nem instalação manual, só o `uv sync` normal.

## Instalação

```bash
uv sync
cp .env.example .env
# edite o .env: SESSION_SECRET, credenciais do admin bootstrap e do MinIO
```

## Chave de cifra das credenciais

As credenciais do MinIO e do SQL Server salvas em `/admin/settings` ficam cifradas no banco local.
Em produção, gere a chave **antes do primeiro deploy** e passe por variável de ambiente, para ela
não ficar na mesma pasta do banco cifrado:

```bash
uv run input-arquivos gerar-chave
# CONFIG_ENCRYPTION_KEY=...   ← cole no .env do servidor (ou num secret do Docker)
```

O comando só imprime a chave: não sobe o app nem cria arquivo. Sem `CONFIG_ENCRYPTION_KEY`, o app
usa (ou cria na primeira execução) `data/.config_encryption_key`, o que é prático para rodar
localmente. **Instalação que já existe:** copie o conteúdo de `data/.config_encryption_key` para
`CONFIG_ENCRYPTION_KEY`. Não gere uma chave nova, senão as credenciais salvas deixam de poder ser
decifradas.

## Executar (Comando Padronizado Universal)

```bash
cd /home/swordpower/Documentos/REPO/PESSOAL/input_arquivos
uv run uvicorn main:app --reload --port 8004
```

A aplicação sobe em `http://127.0.0.1:8004`:

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

## Rotas de sistema (paridade com o app_template)

`GET /api/system/health` e `GET /api/system/metrics` (uptime + contagem de usuários/contexts, nunca dados sensíveis), protegidas por `require_admin` como as demais rotas administrativas. Sem `/api/system/logs`: o projeto não usa o módulo `logging` do Python — a rastreabilidade de uploads já é feita de forma persistente via `/admin/audit`.

Os testes cobrem o pipeline de ingestão (Excel/CSV), a conversão Parquet, o CRUD de contexts e a
criptografia em repouso da configuração do MinIO.

## Validação de dados por coluna

Um context pode ter regras de validação do **conteúdo** de cada coluna. Na listagem de
`/admin/contexts`, cada context tem um botão "Regras" que abre um modal dedicado (separado do
formulário de criação/edição do context) com a tabela de regras: para cada coluna, escolha o tipo
esperado (Texto, Número inteiro, Número decimal, Data ou Sim/Não) e marque "Obrigatória" se a coluna
deve estar sempre presente no arquivo e sem células vazias. O campo "Coluna" sugere, num dropdown,
os nomes vindos do último arquivo aceito para aquele context (`expected_columns`); se ainda não houve
nenhum upload, digite o nome livremente.

Quando um upload chega, cada célula das colunas com regra é conferida contra o tipo declarado (datas
são interpretadas no formato brasileiro DD/MM/AAAA; números decimais aceitam ponto como separador), e
uma regra obrigatória cuja coluna nem veio no arquivo também é rejeitada. Se qualquer célula (ou
coluna) não bater, **o arquivo inteiro é rejeitado** (nada é gravado no destino) e a tela de upload
mostra quais colunas e quantas linhas tiveram problema; a rejeição também fica registrada em
`/admin/audit`.

## Carga em tabela no banco (SQL Server)

O MinIO continua sendo a fonte da verdade: todo upload grava o Parquet lá primeiro. Um context com
**"Carregar no banco de dados"** ligado (em `/admin/contexts`) ganha uma segunda etapa — o mesmo
Parquet é inserido numa tabela do SQL Server configurado em `/admin/settings` — servidor, porta,
banco, usuário e senha em campos separados (usuário e senha cifrados em repouso; a senha nunca volta
pela API). A URL de conexão é montada no servidor com `sqlalchemy.URL.create`, então caracteres como
`@`, `/` e `:` na senha não quebram nada. Driver `pymssql`, sem precisar de ODBC no servidor;
timeout de login de 10s.

- **1 contexto = 1 tabela.** Tabela padrão = slug do nome do context (o mesmo da pasta no MinIO);
  schema padrão = o da conexão (`dbo`). Os dois podem ser trocados no context.
- **Schema criado automaticamente** ao salvar o context (e de novo na carga, se tiver sumido), caso
  ainda não exista — o usuário do banco precisa de `CREATE SCHEMA`. Se a criação falhar (sem
  permissão, banco fora do ar), o context não é salvo e a mensagem aparece no campo Schema.
- **Nomes de coluna normalizados na tabela**: sem acento, minúsculos, `_` no lugar de espaço e
  pontuação (`Valor Líquido` → `valor_liquido`, `2º Trimestre` → `c_2o_trimestre`); nomes que colidem
  ganham `_2`, `_3`. O Parquet no MinIO mantém os nomes originais (as regras de coluna usam eles).
- **Tabela criada no primeiro upload**, com os tipos das regras de coluna (`BIGINT`, `FLOAT`, `DATE`,
  `BIT`, `NVARCHAR(MAX)`; `data_envio` em `DATETIME2`, UTC) e a coluna extra `id_envio` (id do
  registro no audit log). Permissões mínimas do usuário da carga: `CREATE SCHEMA` e `CREATE TABLE`
  no banco (o schema criado por ele já fica sob sua posse), ou, com schema criado pelo DBA,
  `CREATE TABLE` + `ALTER, SELECT, INSERT, DELETE` no schema.
- **Modo de carga por context**: *acumular* (cada envio soma linhas; recarregar um envio apaga só as
  linhas do mesmo `id_envio` antes, então nunca duplica) ou *substituir* (cada envio apaga todo o
  conteúdo da tabela via `DELETE` — sem `DROP`, preservando índices/permissões).
- **Falha no banco não desfaz o upload**: pela tela de upload a carga roda em background e o
  histórico mostra `Banco: pendente/carregado/erro`; via `POST /api/upload` ela roda antes da
  resposta. Um envio com erro de carga (banco fora do ar, coluna nova que a tabela não tem) pode ser
  recarregado em `/admin/audit` → "Recarregar", que lê o Parquet de volta do MinIO.
- **Coluna nova no arquivo** que a tabela não tem é recusada com mensagem clara — adicione a coluna
  na tabela (`ALTER TABLE`) e recarregue.

## Testando sem MinIO (destino "Pasta local")

Além de MinIO, um context pode usar `destination_type = local`: em vez de subir para
um bucket externo, o Parquet (ou o PDF bruto, em modo raw_archive) é salvo direto numa
pasta no disco, com a mesma estrutura de particionamento por data usada no MinIO
(`{pasta_raiz}/{contexto}/{ano}/{mes}/{dia}/arquivo_HHMMSS_uuid.parquet`). Em `/admin/contexts`,
escolha "Pasta local" como destino e informe uma pasta raiz (ex.: `data/local_storage`) — o nome
do contexto já vira subpasta automaticamente, então a mesma raiz pode ser reaproveitada por vários
contexts. Use o botão "Testar/criar pasta local" para confirmar que a pasta é gravável. Isso permite
testar o fluxo completo (upload → conversão → persistência com `data_envio`/`contexto`/`enviado_por`)
sem nenhuma conexão externa.

## Verificação manual ponta a ponta

Sem MinIO disponível, é possível validar toda a lógica de negócio localmente (testes
automatizados acima, ou usando um context do tipo "Pasta local" descrito na seção anterior). Para
validar a integração real com MinIO:

1. Suba uma instância descartável para teste (não faz parte da infraestrutura do projeto):
   ```bash
   docker run -p 9000:9000 -p 9001:9001 minio/minio server /data --console-address ":9001"
   ```
2. Configure o endpoint/credenciais em `/admin/settings` (ou no `.env`) e use o botão "Testar
   conexão". Em `/admin/contexts`, crie um context do tipo MinIO e use "Testar conexão MinIO" para
   confirmar o bucket.
3. Em `/admin/users`, crie um usuário comum (não-admin).
4. Faça login como esse usuário comum em `/` e envie um Excel/CSV/PDF para o context.
5. Confira: o objeto no console do MinIO (com `data_envio`/`contexto`/`enviado_por` corretos) e o
   registro correspondente em `/admin/audit`.
6. Teste um caso de erro proposital (ex.: bucket sem permissão) e confirme que o audit log mostra
   uma mensagem de erro clara, sem stack trace vazando para a UI.
7. Configure uma regra de validação de dados numa coluna (ex.: tipo "Número decimal") e envie um
   arquivo com uma célula inválida nessa coluna — confirme que o upload é rejeitado (nada gravado no
   destino), que a mensagem indica a coluna e a quantidade de linhas com problema, e que a rejeição
   aparece em `/admin/audit`.
8. Confirme que o usuário comum não consegue acessar `/admin` diretamente pela URL.

## Estrutura de pastas

```
input_arquivos/
├── main.py                # cria o FastAPI, monta os arquivos estáticos e inclui as rotas
├── backend/                # tudo que não depende de HTML: API, regras de negócio, persistência
│   ├── config.py            # configurações (variáveis de ambiente/.env)
│   ├── db/                  # engine/sessão SQLAlchemy + bootstrap do banco local
│   ├── models/               # modelos ORM: Context, UploadHistory, User
│   ├── schemas/               # schemas Pydantic da API REST
│   ├── ingestion/             # leitores de arquivo, conversão Parquet e orquestração do pipeline
│   ├── destinations/          # writers de destino (MinIO, pasta local) + registry
│   ├── loaders/                # carga do Parquet em tabela no banco de destino (SQL Server)
│   ├── services/               # camada de serviços (contexts, usuários, upload, auth) + container de DI
│   ├── api/                    # rotas REST (/api/auth, /api/contexts, /api/users, /api/upload(s), /api/audit, /api/system)
│   └── auth/                    # sessão via cookie assinado (session.py) + dependencies do FastAPI
└── frontend/                # tudo que é servido para o navegador
    ├── web/                    # rotas de página (renderizam os templates Jinja2, sem lógica de negócio)
    ├── templates/               # templates Jinja2 (login, upload, admin/*) + base.html (layout Tailwind)
    └── static/
        ├── css/                   # theme.css (corporate/green-neutral/cyber-dark) + estilos não triviais em Tailwind
        └── js/                    # interatividade de cada página (fetch para a API REST)
tests/                    # testes automatizados (pytest)
data/                     # SQLite local de configuração (gitignored)
```

(o pacote Python real fica em `input_arquivos/input_arquivos/` — a pasta acima — dentro da raiz do projeto `input_arquivos/`, onde vivem `pyproject.toml`/`tests/`/`data/`.)

O `frontend/` só conversa com o `backend/` através da API REST (`/api/*`, chamada via `fetch` pelo
JS de cada página) — as rotas de página em `frontend/web/` apenas renderizam o HTML esqueleto e não
acessam serviços/banco diretamente.

## Notas de arquitetura

- **Front-end**: HTML/CSS/JS servidos pelo próprio FastAPI (templates Jinja2 + Tailwind via CDN),
  sem build step nem framework de front-end — a interatividade de cada página é JavaScript puro
  chamando a API REST (`/api/*`).
- **MinIO**: endpoint e credenciais são globais, compartilhados por todos os contexts — cada
  context define apenas o bucket a usar nesse mesmo servidor. Configuráveis via `/admin/settings`
  (cifrados em repouso, sobrepõe o `.env`) ou diretamente no `.env` como fallback.
- **Banco de destino**: uma conexão global de SQL Server em `/admin/settings` (campos separados,
  driver fixo `mssql+pymssql` — não há como apontar para outro tipo de banco); cada context com carga
  ligada define só schema/tabela/modo.
- **Autenticação**: sessão via cookie assinado (`SESSION_SECRET`, ver `backend/auth/session.py`), tanto
  para as páginas quanto para a API REST — toda rota sob `/api/*` (exceto `/api/auth/login`) exige
  login, e as rotas administrativas exigem papel `admin`.
- **Tema**: `corporate` (padrão), `green-neutral` e `cyber-dark`, trocáveis pelo modal de Configurações — mesmo sistema de tokens CSS usado nos demais projetos SwordPower.
