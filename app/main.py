"""FastAPI application factory.

Serves the JSON API under `/api` and the dependency-free Mini App frontend
from `frontend/` on the same origin (so no CORS is required by default).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# Register ORM models on Base.metadata for create_all()/migrations.
import app.models  # noqa: F401
from app.api.errors import register_exception_handlers
from app.api.routes_ads import router as ads_router
from app.api.routes_complaints import router as complaints_router
from app.api.routes_listings import router as listings_router
from app.api.routes_me import router as me_router
from app.api.routes_photos import router as photos_router
from app.api.routes_system import router as system_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.rate_limit import RateLimiter
from app.db import Base, build_engine, build_session_factory
from app.storage import build_storage

logger = logging.getLogger(__name__)

_DEFAULT_FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"


def _frontend_dir(settings: Settings) -> Path:
    if settings.frontend_dir is not None:
        return Path(settings.frontend_dir).resolve()
    return _DEFAULT_FRONTEND_DIR


def build_security_headers(settings: Settings) -> dict[str, str]:
    img_sources = ["'self'", "data:", "blob:"]
    if settings.ad_image_origin:
        img_sources.append(settings.ad_image_origin)
    script_sources = ["'self'", "https://telegram.org"]
    style_sources = ["'self'"]
    if settings.app_docs_enabled:
        # Swagger UI served by FastAPI loads its assets from a CDN.
        script_sources.append("https://cdn.jsdelivr.net")
        style_sources.append("https://cdn.jsdelivr.net")
        img_sources.append("https://fastapi.tiangolo.com")
    frame_ancestors = " ".join(settings.frame_ancestors) or "'self'"
    csp = "; ".join(
        (
            "default-src 'self'",
            "base-uri 'none'",
            "object-src 'none'",
            "form-action 'none'",
            f"script-src {' '.join(script_sources)}",
            f"style-src {' '.join(style_sources)}",
            f"img-src {' '.join(img_sources)}",
            "font-src 'self'",
            "connect-src 'self'",
            "manifest-src 'self'",
            f"frame-ancestors {frame_ancestors}",
        )
    )
    headers = {
        "Content-Security-Policy": csp,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
        "X-Permitted-Cross-Domain-Policies": "none",
        "Cross-Origin-Resource-Policy": "same-origin",
        "Cross-Origin-Opener-Policy": "same-origin",
    }
    if settings.is_production:
        headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return headers


def _client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(app_settings)
        app.state.settings = app_settings
        app.state.session_factory = build_session_factory(engine)
        app.state.storage = build_storage(app_settings)
        app.state.rate_limiter = RateLimiter()
        if app_settings.app_auto_create_tables:
            Base.metadata.create_all(engine)
            logger.warning(
                "APP_AUTO_CREATE_TABLES is enabled; use `alembic upgrade head` instead"
            )
        logger.info("API started with settings %s", app_settings.safe_summary())
        try:
            yield
        finally:
            engine.dispose()

    docs_enabled = app_settings.app_docs_enabled
    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        docs_url="/api/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    app.state.settings = app_settings

    security_headers = build_security_headers(app_settings)
    ip_limit = app_settings.rate_limit_requests_per_minute_per_ip

    @app.middleware("http")
    async def security_and_limits(request: Request, call_next):
        path = request.url.path
        if (
            ip_limit > 0
            and path.startswith("/api/")
            and path != "/api/health"
            and not path.startswith("/api/photos/")
        ):
            limiter: RateLimiter = request.app.state.rate_limiter
            allowed, retry_after = limiter.hit(
                f"ip:{_client_ip(request, app_settings)}", ip_limit, 60
            )
            if not allowed:
                response = JSONResponse(
                    status_code=429,
                    content={
                        "error": {
                            "code": "rate_limited",
                            "message": "Слишком много запросов. Попробуйте позже.",
                        }
                    },
                )
                response.headers["Retry-After"] = str(retry_after)
                for name, value in security_headers.items():
                    response.headers.setdefault(name, value)
                return response

        response = await call_next(request)
        for name, value in security_headers.items():
            response.headers.setdefault(name, value)
        return response

    if app_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Telegram-Init-Data"],
            max_age=600,
        )
    if "*" not in app_settings.host_allowlist:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=app_settings.host_allowlist)

    register_exception_handlers(app)
    app.include_router(system_router)
    app.include_router(ads_router)
    app.include_router(me_router)
    app.include_router(listings_router)
    app.include_router(complaints_router)
    app.include_router(photos_router)

    frontend_dir = _frontend_dir(app_settings)
    if frontend_dir.is_dir():
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
    else:
        logger.warning("Frontend directory %s not found; API only", frontend_dir)

        @app.get("/", include_in_schema=False)
        def root_fallback() -> JSONResponse:
            return JSONResponse(
                {
                    "service": app_settings.app_name,
                    "message": "Frontend is not built. The API is available under /api.",
                }
            )

    return app


app = create_app()
