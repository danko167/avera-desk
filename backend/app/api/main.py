import logging
import time
from hmac import compare_digest

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..core.logging import log_exception
from ..core.local_security import (
    LOCAL_AUTH_HEADER,
    get_local_auth_token,
    parse_allowed_origins,
    should_enforce_local_auth,
)
from .lifecycle import lifespan
from .routers import api_router, root_router
from .routers.ws import router as ws_router

logger = logging.getLogger(__name__)

_ALLOWED_ORIGINS = parse_allowed_origins()
_LOCAL_AUTH_EXEMPT_PATHS = {
    "/health",
    "/api/local-auth/token",
    "/api/oauth/callback",
    "/api/oauth/google/callback",
}
_STARTUP_TRACE_PATHS = {
    "/api/local-auth/token",
    "/api/settings",
}


def _local_auth_rejected_response(request: Request) -> JSONResponse:
    headers: dict[str, str] = {}
    origin = (request.headers.get("origin") or "").strip().rstrip("/")
    if origin and origin in _ALLOWED_ORIGINS:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Vary"] = "Origin"
        headers["Access-Control-Allow-Headers"] = f"Content-Type, {LOCAL_AUTH_HEADER}"
    return JSONResponse(
        status_code=401,
        content={"detail": "Missing or invalid local auth token."},
        headers=headers,
    )


def _log_startup_request_end(
    *,
    trace_enabled: bool,
    method: str,
    path: str,
    status_code: int,
    started: float,
) -> None:
    if not trace_enabled:
        return

    logger.info(
        "startup_request_end method=%s path=%s status=%s duration_ms=%.2f",
        method,
        path,
        status_code,
        (time.perf_counter() - started) * 1000,
    )


app = FastAPI(title="Avera Desk API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", LOCAL_AUTH_HEADER],
)


@app.middleware("http")
async def require_local_auth_token(request, call_next):
    started = time.perf_counter()
    path = request.url.path
    trace_startup_path = path in _STARTUP_TRACE_PATHS
    if trace_startup_path:
        logger.info(
            "startup_request_begin method=%s path=%s client=%s origin=%s has_local_token=%s",
            request.method,
            path,
            request.client.host if request.client is not None else None,
            request.headers.get("origin"),
            bool((request.headers.get(LOCAL_AUTH_HEADER) or "").strip()),
        )

    if not should_enforce_local_auth():
        try:
            response = await call_next(request)
        except Exception as exc:
            if trace_startup_path:
                log_exception(
                    logger,
                    "request_exception",
                    exc,
                    method=request.method,
                    path=path,
                    client=request.client.host if request.client is not None else None,
                    origin=request.headers.get("origin"),
                    has_local_token=bool((request.headers.get(LOCAL_AUTH_HEADER) or "").strip()),
                )
            raise
        _log_startup_request_end(
            trace_enabled=trace_startup_path,
            method=request.method,
            path=path,
            status_code=response.status_code,
            started=started,
        )
        return response

    if request.method == "OPTIONS":
        response = await call_next(request)
        _log_startup_request_end(
            trace_enabled=trace_startup_path,
            method=request.method,
            path=path,
            status_code=response.status_code,
            started=started,
        )
        return response
    if path in _LOCAL_AUTH_EXEMPT_PATHS:
        response = await call_next(request)
        _log_startup_request_end(
            trace_enabled=trace_startup_path,
            method=request.method,
            path=path,
            status_code=response.status_code,
            started=started,
        )
        return response
    if path.startswith("/api/"):
        provided_token = (request.headers.get(LOCAL_AUTH_HEADER) or "").strip()
        if not provided_token or not compare_digest(provided_token, get_local_auth_token()):
            logger.warning(
                "local_auth_rejected method=%s path=%s client=%s origin=%s has_local_token=%s",
                request.method,
                path,
                request.client.host if request.client is not None else None,
                request.headers.get("origin"),
                bool(provided_token),
            )
            return _local_auth_rejected_response(request)

    try:
        response = await call_next(request)
    except Exception as exc:
        if trace_startup_path:
            log_exception(
                logger,
                "request_exception",
                exc,
                method=request.method,
                path=path,
                client=request.client.host if request.client is not None else None,
                origin=request.headers.get("origin"),
                has_local_token=bool((request.headers.get(LOCAL_AUTH_HEADER) or "").strip()),
            )
        raise

    _log_startup_request_end(
        trace_enabled=trace_startup_path,
        method=request.method,
        path=path,
        status_code=response.status_code,
        started=started,
    )
    return response

app.include_router(root_router)
app.include_router(api_router)
app.include_router(ws_router)
