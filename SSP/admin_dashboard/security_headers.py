# admin_dashboard/security_headers.py
#
# Security headers on every dashboard response (issue #162): defence in depth
# for a surface that can change inventory, settings, cash collections and
# owed payments. The CSP allows scripts and styles only from the dashboard's
# own /static files, so the templates carry no inline <script> code, on*=
# handlers or style= attributes (tests/test_dashboard_security_headers.py
# checks both).

from starlette.middleware.base import BaseHTTPMiddleware

CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data:",
    "object-src 'none'",
    "base-uri 'none'",
    "frame-ancestors 'none'",
    "form-action 'self'",
])

SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

STATIC_PREFIX = "/static/"
# FastAPI's /docs and /redoc pages load their scripts from a CDN and inline,
# so the CSP would blank them. They exist only with API_DOCS_ENABLED (off on
# a kiosk); they get every header but the CSP.
API_DOCS_PATHS = ("/docs", "/redoc")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        path = request.url.path
        for name, value in SECURITY_HEADERS.items():
            if name == "Content-Security-Policy" and path.startswith(API_DOCS_PATHS):
                continue
            response.headers[name] = value
        # Pages and JSON can show sales and counts: keep them out of the
        # browser cache. The vendored /static files may be cached.
        if not path.startswith(STATIC_PREFIX):
            response.headers["Cache-Control"] = "no-store"
        return response
