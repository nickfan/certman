from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException

from certman.api.routes.certificates import router as certificates_router
from certman.api.routes.config import router as config_router
from certman.api.routes.health import router as health_router
from certman.api.routes.jobs import router as jobs_router
from certman.api.routes.nodes import router as nodes_router
from certman.api.routes.node_agent import router as node_agent_router
from certman.api.routes.webhooks import router as webhooks_router
from certman.config import create_runtime, resolve_runtime_path
from certman.events import EventBus
from certman.services.webhook_service import WebhookService


OPENAPI_TAGS = [
    {"name": "health", "description": "Runtime health and readiness endpoints."},
    {"name": "certificates", "description": "Certificate issuance and renewal job submission APIs."},
    {"name": "jobs", "description": "Queued/running/completed job query APIs."},
    {"name": "webhooks", "description": "Webhook subscription management APIs."},
    {"name": "nodes", "description": "Node registration APIs."},
    {"name": "node-agent", "description": "Signed polling and result reporting APIs for node agents."},
    {"name": "config", "description": "Read-only merged config query and validation APIs."},
]


OPENAPI_DESCRIPTION = """
CertMan control-plane HTTP API.

Documentation endpoints:
- `/docs`: Swagger UI
- `/redoc`: ReDoc
- `/openapi.json`: machine-readable OpenAPI schema

Notes:
- `/health` is the only endpoint that does not use the `ApiResponse` envelope.
- The current AI integration surface is REST + OpenAPI; MCP access is provided by the `certman-mcp` stdio server.
""".strip()


def create_app(*, data_dir: str = "data", config_file: str | None = None) -> FastAPI:
    runtime = create_runtime(data_dir=data_dir, config_file=config_file)
    if runtime.config.server is None:
        raise ValueError("server mode requires [server] configuration block")
    db_path = resolve_runtime_path(runtime, runtime.config.server.db_path)
    event_bus = EventBus()
    webhook_service = WebhookService(db_path=db_path)

    for topic in ["job.queued", "job.completed", "job.failed"]:
        event_bus.subscribe(
            topic,
            lambda event, service=webhook_service: service.publish_event(topic=event.topic, payload=event.payload),
        )

    app = FastAPI(
        title="CertMan Control Plane",
        version="0.1.0",
        summary="Control-plane API for certificate jobs, nodes, agents, and webhooks",
        description=OPENAPI_DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=OPENAPI_TAGS,
    )
    app.state.runtime = runtime
    app.state.event_bus = event_bus
    app.state.webhook_service = webhook_service
    app.include_router(health_router)
    app.include_router(config_router)
    app.include_router(certificates_router)
    app.include_router(jobs_router)
    app.include_router(nodes_router)
    app.include_router(node_agent_router)
    app.include_router(webhooks_router)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "HTTP_ERROR", "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content={"success": False, "data": None, "error": detail})

    return app
