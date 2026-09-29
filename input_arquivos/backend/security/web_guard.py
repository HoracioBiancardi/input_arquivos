"""Cabeçalhos de segurança (CSP incluso) e recusa de requisições de outra origem (padrão app_template).

O cookie de sessão já é `SameSite=Strict`, mas "site" é o domínio registrável: outra
porta do mesmo host ou outro subdomínio do mesmo domínio contam como o mesmo site e o
navegador envia o cookie. Por isso POST/PUT/PATCH/DELETE em `/api/*` marcados pelo
navegador como de outra origem (`Sec-Fetch-Site: same-site`/`cross-site`) são recusados.
Clientes que não são navegador não mandam o cabeçalho e seguem pela sessão normal.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_STATE_CHANGING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_SAME_ORIGIN = frozenset({"same-origin", "none"})

# Content-Security-Policy: de onde a página pode carregar código.
# - script-src 'self': só os .js do próprio app, nada inline nem de outro site. Um XSS que
#   consiga injetar <img onerror=...> ou <script> não executa (por isso os templates não
#   usam onclick="": as ações ficam em data-click, tratadas em common.js).
# - style/font: CSS inline (atributos style="") e as fontes/ícones do Google Fonts.
# - frame-ancestors 'none': ninguém põe o app num <iframe> (clickjacking).
# - base-uri/form-action: links relativos e formulários não podem apontar para fora.
_CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class WebGuardMiddleware(BaseHTTPMiddleware):
    """Recusa escrita de outra origem em `/api/*` e põe cabeçalhos de segurança em tudo."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path
        if (
            path.startswith("/api/")
            and request.method in _STATE_CHANGING
            and request.headers.get("sec-fetch-site", "same-origin") not in _SAME_ORIGIN
        ):
            return JSONResponse({"detail": "Requisição de outra origem recusada."}, status_code=403)
        response = await call_next(request)
        if path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Content-Security-Policy", _CONTENT_SECURITY_POLICY)
        # O navegador respeita o tipo declarado do arquivo e não "adivinha" (texto não vira script).
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        # Links para outros sites não levam a URL do app (que pode ter ids de envio).
        response.headers.setdefault("Referrer-Policy", "same-origin")
        # O app não usa câmera, microfone nem localização: bloqueados de vez.
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response
