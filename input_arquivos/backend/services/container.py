"""Container de serviços: instancia e compartilha os serviços da aplicação em um único lugar."""

from input_arquivos.backend.db.session import DatabaseSessionFactory, get_session_factory
from input_arquivos.backend.destinations.registry import DestinationWriterRegistry
from input_arquivos.backend.ingestion.pipeline import IngestionPipeline
from input_arquivos.backend.services.auth_service import AuthService
from input_arquivos.backend.services.context_service import ContextService
from input_arquivos.backend.services.preview_service import PreviewService
from input_arquivos.backend.services.system_settings_service import SystemSettingsService
from input_arquivos.backend.services.upload_service import UploadService
from input_arquivos.backend.services.user_context_service import UserContextService
from input_arquivos.backend.services.user_service import UserService


class ServiceContainer:
    """Agrupa as instâncias dos serviços de aplicação, evitando reconstruí-los a cada uso."""

    def __init__(self, session_factory: DatabaseSessionFactory) -> None:
        """Inicializa o container e todos os serviços que ele expõe.

        Args:
            session_factory: Fábrica de sessões do banco de configuração local,
                compartilhada por todos os serviços.
        """
        self.auth_service = AuthService(session_factory)
        self.context_service = ContextService(session_factory)
        self.user_service = UserService(session_factory, self.auth_service)
        self.user_context_service = UserContextService(session_factory, self.context_service)
        self.upload_service = UploadService(
            session_factory=session_factory,
            context_service=self.context_service,
            pipeline=IngestionPipeline(),
            writer_registry=DestinationWriterRegistry(),
        )
        self.preview_service = PreviewService(session_factory=session_factory)
        self.system_settings_service = SystemSettingsService(session_factory)


_container: ServiceContainer | None = None


def get_container() -> ServiceContainer:
    """Retorna a instância única (singleton) do container de serviços da aplicação.

    Returns:
        Instância de `ServiceContainer` compartilhada por toda a aplicação.
    """
    global _container
    if _container is None:
        _container = ServiceContainer(get_session_factory())
    return _container
