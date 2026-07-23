"""Modelo ORM de UploadHistory: log de auditoria de cada arquivo enviado."""

import enum
from datetime import datetime, timezone

from sqlalchemy import Enum as SqlEnum
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.context import DestinationType, WriteMode


class UploadStatus(str, enum.Enum):
    """Resultado final do processamento de um upload."""

    SUCCESS = "success"
    ERROR = "error"


class UploadHistory(Base):
    """Registro de auditoria de um upload processado pelo sistema.

    Attributes:
        id: Identificador interno do registro.
        filename: Nome original do arquivo enviado.
        context_name: Nome do contexto usado no momento do upload (mantido
            mesmo que o contexto seja editado/desativado depois).
        destination_type: Tipo de destino para o qual os dados foram enviados.
        destination_detail: Detalhe do destino final (ex.: chave do objeto no
            MinIO, ou "schema.tabela" no SQL Server).
        write_mode: Modo de escrita usado (apenas relevante para destinos de banco).
        status: Resultado do processamento (sucesso ou erro).
        row_count: Quantidade de linhas geradas, quando aplicável.
        error_message: Mensagem de erro amigável, quando `status` é ERROR.
        uploaded_by: Nome de usuário de quem realizou o upload (sempre
            preenchido, pois o login é obrigatório para qualquer usuário).
        created_at: Data/hora do upload.
    """

    __tablename__ = "upload_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(500))
    context_name: Mapped[str] = mapped_column(String(100), index=True)
    destination_type: Mapped[DestinationType] = mapped_column(SqlEnum(DestinationType))
    destination_detail: Mapped[str] = mapped_column(String(1000))
    write_mode: Mapped[WriteMode | None] = mapped_column(SqlEnum(WriteMode), default=None)
    status: Mapped[UploadStatus] = mapped_column(SqlEnum(UploadStatus))
    row_count: Mapped[int | None] = mapped_column(default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    uploaded_by: Mapped[str] = mapped_column(String(150), index=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc), index=True)
