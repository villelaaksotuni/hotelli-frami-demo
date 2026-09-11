import asyncio
from contextlib import asynccontextmanager, suppress
import logging

from fastapi import FastAPI
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config.settings import settings
from app.path_prefix import normalize_path_prefix, path_has_prefix, strip_path_prefix
from app.routes.admin_prompt import router as admin_prompt_router
from app.routes.availability import router as availability_router
from app.routes.dashboard import router as dashboard_router
from app.routes.feedback import router as feedback_router
from app.routes.health import router as health_router
from app.routes.live import router as live_router
from app.routes.voice import router as voice_router
from app.services.daily_summary_scheduler import DailySummaryScheduler
from app.services.daily_summary import daily_summary_service

logger = logging.getLogger(__name__)


class PublicPathPrefixMiddleware:
    def __init__(self, app: ASGIApp, path_prefix: str):
        self.app = app
        self.path_prefix = normalize_path_prefix(path_prefix)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"} or not self.path_prefix:
            await self.app(scope, receive, send)
            return

        adjusted_scope = dict(scope)
        adjusted_scope["root_path"] = self.path_prefix

        path = scope.get("path", "")
        if path_has_prefix(path, self.path_prefix):
            adjusted_scope["path"] = strip_path_prefix(path, self.path_prefix)

        await self.app(adjusted_scope, receive, send)


def _log_registered_routes(application: FastAPI) -> None:
    for route in application.routes:
        path = getattr(route, "path", None)
        methods = sorted(getattr(route, "methods", []) or [])
        name = getattr(route, "name", None)
        logger.info(
            "[startup] route_registered path=%s methods=%s name=%s",
            path,
            methods,
            name,
        )


def _log_runtime_configuration() -> None:
    logger.info(
        "[startup] data_dir=%s prompt_store=%s public_base_url_set=%s "
        "public_path_prefix=%s twilio_configured=%s openai_configured=%s strict_validation=%s",
        settings.app_data_dir,
        settings.prompt_store_path,
        bool(settings.normalized_public_base_url),
        settings.public_url_path_prefix or "/",
        settings.has_complete_twilio_config,
        settings.has_openai_credentials,
        settings.validate_startup_dependencies,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _log_runtime_configuration()
    settings.validate_runtime_dependencies()
    # Deliberately unconditional: VALIDATE_STARTUP_DEPENDENCIES defaults to false,
    # so gating this guard behind that flag (like validate_startup below) would
    # silently skip it on every default deployment.
    settings.validate_no_legacy_booking_config()
    if settings.validate_startup_dependencies:
        settings.validate_startup()
    _log_registered_routes(app)

    scheduler_task: asyncio.Task[None] | None = None
    if settings.daily_summary_auto_send_enabled and settings.daily_summary_to_phone:
        scheduler = DailySummaryScheduler(
            summary_service=daily_summary_service,
            timezone_name=settings.daily_summary_timezone,
            send_time=settings.daily_summary_send_time,
        )
        scheduler_task = asyncio.create_task(scheduler.run_forever())
        logger.info(
            "[startup] daily_summary_scheduler_started timezone=%s send_time=%s to_phone_configured=%s",
            settings.daily_summary_timezone,
            settings.daily_summary_send_time,
            bool(settings.daily_summary_to_phone),
        )
    else:
        logger.info(
            "[startup] daily_summary_scheduler_disabled enabled=%s to_phone_configured=%s",
            settings.daily_summary_auto_send_enabled,
            bool(settings.daily_summary_to_phone),
        )

    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            with suppress(asyncio.CancelledError):
                await scheduler_task


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    PublicPathPrefixMiddleware,
    path_prefix=settings.public_url_path_prefix,
)
app.include_router(health_router)
app.include_router(dashboard_router)
app.include_router(voice_router)
app.include_router(availability_router)
app.include_router(admin_prompt_router)
app.include_router(feedback_router)
app.include_router(live_router)
