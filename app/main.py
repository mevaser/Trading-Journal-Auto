from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import auth, fills, trades
from app.observability import (
    AppError,
    ErrorCode,
    clear_auth_context,
    clear_request_id,
    configure_logging,
    get_logger,
    get_request_id,
    set_request_id,
)

configure_logging()

app = FastAPI(title="Trading Journal API")
logger = get_logger("app.request")
error_logger = get_logger("app.error")


def _error_payload(
    *,
    request: Request,
    code: str,
    message: str,
    details: object,
    retryable: bool,
) -> dict[str, object]:
    request_id = get_request_id() or getattr(request.state, "request_id", None)
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": request_id,
            "retryable": retryable,
        },
        # Keep top-level request_id for backward compatibility with existing clients/tests.
        "request_id": request_id,
    }


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    set_request_id(request_id)

    started_at = time.perf_counter()
    try:
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "request_completed",
            extra={
                "event": "request_completed",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": elapsed_ms,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        clear_auth_context()
        clear_request_id()


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    error_logger.warning(
        "app_error",
        extra={
            "event": "app_error",
            "method": request.method,
            "path": request.url.path,
            "status_code": exc.status_code,
            "error_code": exc.code,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_payload(
            request=request,
            code=str(exc.code),
            message=exc.message,
            details=exc.details,
            retryable=False,
        ),
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    error_logger.warning(
        "request_validation_error",
        extra={
            "event": "request_validation_error",
            "method": request.method,
            "path": request.url.path,
            "status_code": 422,
            "error_code": ErrorCode.REQUEST_VALIDATION,
        },
    )
    return JSONResponse(
        status_code=422,
        content=_error_payload(
            request=request,
            code=str(ErrorCode.REQUEST_VALIDATION),
            message="Request validation failed",
            details=jsonable_encoder(exc.errors()),
            retryable=False,
        ),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    error_logger.exception(
        "unhandled_error",
        extra={
            "event": "unhandled_error",
            "method": request.method,
            "path": request.url.path,
            "status_code": 500,
            "error_code": ErrorCode.INTERNAL_ERROR,
        },
    )
    return JSONResponse(
        status_code=500,
        content=_error_payload(
            request=request,
            code=str(ErrorCode.INTERNAL_ERROR),
            message="Internal server error",
            details=None,
            retryable=True,
        ),
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(trades.router)
app.include_router(fills.router)


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Trading Journal API is live"}
