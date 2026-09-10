from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config.settings import settings

router = APIRouter()


@router.get("/healthz")
async def healthcheck(request: Request):
    raw_path = request.scope.get("raw_path", b"")
    if isinstance(raw_path, bytes):
        raw_path = raw_path.decode("utf-8", errors="replace")

    return JSONResponse(
        content={
            "status": "ok",
            "public_base_url_configured": bool(settings.normalized_public_base_url),
            "configured_public_path_prefix": settings.public_url_path_prefix or "/",
            "openai_configured": settings.has_openai_credentials,
            "twilio_configured": settings.has_complete_twilio_config,
            "app_data_dir": settings.app_data_dir,
            "request_root_path": request.scope.get("root_path") or "",
            "request_path": request.scope.get("path") or "",
            "request_raw_path": raw_path,
            "request_url_path": request.url.path,
            "request_host": request.headers.get("host"),
            "x_forwarded_host": request.headers.get("x-forwarded-host"),
            "x_forwarded_proto": request.headers.get("x-forwarded-proto"),
            "x_forwarded_prefix": request.headers.get("x-forwarded-prefix"),
        }
    )
