from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from api.routers import convert, fhir, health
from api.routers.mcp import mount_mcp
from api.routers.v1 import detect as v1_detect
from api.routers.v1 import infer as v1_infer
from api.routers.v1 import validate as v1_validate

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    from core.logging import configure_logging
    from core.settings import settings

    configure_logging(level=settings.log_level, fmt="json" if settings.env == "production" else "console")
    log.info("api_startup", env=settings.env, version="0.1.0")

    _setup_otel(app)
    mount_mcp(app)

    yield

    log.info("api_shutdown")


def _setup_otel(app: FastAPI) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        log.warning("otel_instrumentation_failed")


def create_app() -> FastAPI:
    app = FastAPI(
        title="FHIR-Forge API",
        version="0.1.0",
        description="Pipeline híbrido (LLM + SUSHI + validators) para BR Core e RNDS",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next: Any) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        from core.logging import request_id_var

        token = request_id_var.set(request_id)
        try:
            response: Response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(health.router)
    app.include_router(convert.router)
    app.include_router(fhir.router)

    # v1 — versioned routes (atomic pipeline). Legacy routes remain intact.
    app.include_router(v1_detect.router, prefix="/v1")
    app.include_router(v1_infer.router, prefix="/v1")
    app.include_router(v1_validate.router, prefix="/v1")

    return app


app = create_app()
