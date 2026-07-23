"""Rota da API REST para envio programático de arquivos, reaproveitando o mesmo UploadService da UI."""

from fastapi import APIRouter, Form, HTTPException, UploadFile

from app.models.context import WriteMode
from app.schemas.upload import UploadHistoryResponse
from app.services.container import get_container
from app.services.upload_service import ContextNotFoundError

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", response_model=UploadHistoryResponse)
async def upload_file(
    file: UploadFile,
    context_name: str = Form(...),
    uploaded_by: str = Form(...),
    write_mode: WriteMode | None = Form(default=None),
) -> UploadHistoryResponse:
    """Processa um arquivo enviado via API, usando o mesmo pipeline da tela de upload.

    Args:
        file: Arquivo enviado (Excel, CSV ou PDF).
        context_name: Nome do context de destino.
        uploaded_by: Nome de quem está realizando o upload.
        write_mode: Modo de escrita, relevante apenas para contexts de banco de dados.

    Returns:
        O registro de audit log criado para este upload.

    Raises:
        HTTPException: 404 se o context informado não existir ou estiver inativo.
    """
    upload_service = get_container().upload_service
    file_bytes = await file.read()
    try:
        history = upload_service.process_upload(
            file_bytes=file_bytes,
            filename=file.filename or "arquivo_sem_nome",
            context_name=context_name,
            write_mode=write_mode,
            uploaded_by=uploaded_by,
        )
    except ContextNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return UploadHistoryResponse.model_validate(history)
