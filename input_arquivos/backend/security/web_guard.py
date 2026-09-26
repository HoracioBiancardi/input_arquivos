"""Cabeçalhos de segurança e recusa de requisições de outra origem (padrão app_template).

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
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response
