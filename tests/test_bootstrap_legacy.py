"""Banco criado por versão antiga: colunas removidas do modelo e ainda `NOT NULL` impediam salvar contexto."""

import sqlite3

from input_arquivos.backend.db.bootstrap import DatabaseBootstrapper
from input_arquivos.backend.db.session import DatabaseSessionFactory
from input_arquivos.backend.models.context import Context
from input_arquivos.backend.services.auth_service import AuthService


def test_colunas_antigas_obrigatorias_saem_e_os_dados_ficam(tmp_path):
    caminho = tmp_path / "antigo.db"
    con = sqlite3.connect(caminho)
    con.executescript(
        """
        CREATE TABLE contexts (
            id INTEGER NOT NULL, name VARCHAR(100) NOT NULL, destination_type VARCHAR(9) NOT NULL,
            minio_bucket VARCHAR(255), db_schema_name VARCHAR(100) NOT NULL, local_path VARCHAR(500),
            default_write_mode VARCHAR(10) NOT NULL, pdf_mode VARCHAR(14) NOT NULL, image_mode VARCHAR(16) NOT NULL,
            allowed_file_types VARCHAR(50) NOT NULL, active BOOLEAN NOT NULL,
            created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, PRIMARY KEY (id), UNIQUE (name)
        );
        INSERT INTO contexts VALUES (7, 'Vendas', 'LOCAL', NULL, 'dbo', 'data/x', 'append', 'METADATA_ONLY',
            'RAW_ARCHIVE', 'excel', 1, '2026-01-01 00:00:00', '2026-01-01 00:00:00');
        """
    )
    con.commit()
    con.close()

    fabrica = DatabaseSessionFactory(f"sqlite:///{caminho}")
    DatabaseBootstrapper(fabrica, AuthService(fabrica)).run()

    with fabrica.session() as sessao:
        sessao.add(Context(name="Novo", destination_type="local", allowed_file_types="csv"))
    with fabrica.session() as sessao:
        nomes = sorted(c.name for c in sessao.query(Context).all())
    assert nomes == ["Novo", "Vendas"]
    colunas = [r[1] for r in sqlite3.connect(caminho).execute("pragma table_info(contexts)")]
    assert "db_schema_name" not in colunas and "default_write_mode" not in colunas
