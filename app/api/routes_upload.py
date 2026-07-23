"""Rotas da API REST de upload: envio programático (headless) e o fluxo interativo da tela de upload."""

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile

from app.auth.dependencies import require_login
from app.auth.session import SessionUser
from app.models.context import WriteMode
from app.schemas.upload import UploadHistoryResponse
from app.services.container import get_container
from app.services.upload_service import ContextNotFoundError

router = APIRouter(prefix="/api", tags=["upload"], dependencies=[Depends(require_login)])


@router.post("/upload", response_model=UploadHistoryResponse)
async def upload_file(
    file: UploadFile,
    context_name: str = Form(...),
    uploaded_by: str = Form(...),
    write_mode: WriteMode | None = Form(default=None),
) -> UploadHistoryResponse:
    """Processa um arquivo enviado via API, usando o mesmo pipeline da tela de upload.

    Não pede confirmação em caso de divergência de colunas: usado para envio
    programático, onde não há um humano para decidir.

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


@router.post("/uploads", response_model=UploadHistoryResponse)
async def upload_interactive(
    file: UploadFile,
    context_name: str = Form(...),
    write_mode: WriteMode | None = Form(default=None),
    confirm_mismatch: bool = Form(default=False),
    cancelled: bool = Form(default=False),
    user: SessionUser = Depends(require_login),
) -> UploadHistoryResponse:
    """Processa um arquivo enviado pela tela de upload, com confirmação de divergência de colunas.

    Fluxo: se as colunas do arquivo divergirem das do último arquivo aceito
    para o context e `confirm_mismatch` não tiver sido enviado como `true`,
    a requisição falha com 409 e nada é persistido — o front-end deve então
    reenviar o mesmo arquivo com `confirm_mismatch=true` (usuário confirmou)
    ou com `cancelled=true` (usuário cancelou, registra o cancelamento como
    erro no audit log).

    Args:
        file: Arquivo enviado (Excel, CSV ou PDF).
        context_name: Nome do context de destino.
        write_mode: Modo de escrita, relevante apenas para contexts de banco de dados.
        confirm_mismatch: Se o usuário já confirmou o envio apesar da divergência de colunas.
        cancelled: Se o usuário cancelou o envio após ver a divergência de colunas.
        user: Usuário autenticado na sessão atual.

    Returns:
        O registro de audit log criado para este upload.

    Raises:
        HTTPException: 404 se o context não existir/estiver inativo, 422 se
            faltar alguma coluna obrigatória configurada para o context, ou
            409 se houver divergência de colunas ainda não confirmada pelo usuário.
    """
    container = get_container()
    try:
        context = container.upload_service.resolve_context(context_name)
    except ContextNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    filename = file.filename or "arquivo_sem_nome"
    username = user.username

    if cancelled:
        history = container.upload_service.record_error(
            context,
            filename,
            write_mode,
            username,
            "Envio cancelado pelo usuário: colunas diferentes do último arquivo aceito para este contexto.",
        )
        return UploadHistoryResponse.model_validate(history)

    file_bytes = await file.read()

    try:
        artifact = container.upload_service.build_artifact(file_bytes, filename, context, username)
    except Exception as error:  # noqa: BLE001 - erro de leitura vira registro de auditoria
        history = container.upload_service.record_error(context, filename, write_mode, username, str(error))
        return UploadHistoryResponse.model_validate(history)

    required_violation = container.upload_service.check_required_columns(context, artifact)
    if required_violation is not None:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Este arquivo não atende às colunas obrigatórias configuradas para este contexto.",
                "missing_columns": required_violation.missing_columns,
                "empty_columns": required_violation.empty_columns,
            },
        )

    if not confirm_mismatch:
        mismatch = container.upload_service.check_column_mismatch(context, artifact)
        if mismatch is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Este arquivo tem colunas diferentes das do último arquivo aceito para este contexto.",
                    "missing_columns": mismatch.missing_columns,
                    "extra_columns": mismatch.extra_columns,
                },
            )

    history = container.upload_service.finalize(artifact, context, write_mode, filename, username)
    if history.status.value == "success":
        container.user_service.set_last_context(user.user_id, context.name)
    return UploadHistoryResponse.model_validate(history)


@router.get("/uploads/recent", response_model=list[UploadHistoryResponse])
def list_recent_uploads(limit: int = 20) -> list[UploadHistoryResponse]:
    """Lista os uploads mais recentes, para exibição na tela principal.

    Args:
        limit: Quantidade máxima de registros a retornar.

    Returns:
        Lista de `UploadHistory` convertida para `UploadHistoryResponse`.
    """
    history = get_container().upload_service.list_recent(limit=limit)
    return [UploadHistoryResponse.model_validate(item) for item in history]
