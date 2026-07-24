@~/.claude/python-code-standards.md

# Sistema de Ingestão de Arquivos

FastAPI + Jinja2 + JavaScript puro (sem NiceGUI nem outro framework de front-end): upload de
Excel/CSV/PDF, conversão para Parquet e envio para MinIO ou SQL Server, conforme o contexto de
negócio selecionado (ex.: "vendas"). Cada contexto pode ter regras de validação de tipo/obrigatoriedade
por coluna, que rejeitam o upload inteiro se algum dado não bater. Área administrativa (`/admin`)
gerencia contexts (incluindo essas regras), usuários e audit log.

Ver `README.md` para instruções de instalação e execução.
