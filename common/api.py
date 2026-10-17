import asyncio
import contextvars
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from common.contracts import uid

request_id = contextvars.ContextVar("request_id", default="-")
log = logging.getLogger("refill")


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, retryable: bool = False):
        self.code, self.message, self.status, self.retryable = code, message, status, retryable


class JSONLog(logging.Formatter):
    def format(self, record):
        value = {
            "time": self.formatTime(record),
            "level": record.levelname,
            "request_id": request_id.get(),
        }
        value.update(
            record.msg if isinstance(record.msg, dict) else {"message": record.getMessage()}
        )
        return json.dumps(value)


def setup_logging():
    if not log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONLog())
        log.addHandler(handler)
        log.setLevel(logging.INFO)


def create_api(name: str, lifespan=None) -> FastAPI:
    setup_logging()
    app = FastAPI(title=f"Refill Assist {name}", version="1.0", lifespan=lifespan)
    app.add_middleware(BodyLimit, maximum=26_000_000)

    @app.middleware("http")
    async def trace(request: Request, call_next):
        incoming = request.headers.get("x-request-id", "")
        rid = (
            incoming
            if 0 < len(incoming) <= 100 and all(c.isalnum() or c in "-_." for c in incoming)
            else uid()
        )
        token = request_id.set(rid)
        start = time.monotonic()
        try:
            try:
                response = await call_next(request)
            except Exception as error:
                log.error("Unhandled service error: %s", type(error).__name__)
                response = JSONResponse(
                    status_code=500,
                    content={
                        "error": {
                            "code": "internal_error",
                            "message": "The service could not complete the request",
                            "request_id": rid,
                            "retryable": True,
                        }
                    },
                )
            response.headers["x-request-id"] = rid
            log.info(
                {
                    "service": name,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "elapsed_ms": round((time.monotonic() - start) * 1000),
                }
            )
            return response
        finally:
            request_id.reset(token)

    @app.exception_handler(ApiError)
    async def known_error(request, exc):
        return JSONResponse(
            status_code=exc.status,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": request_id.get(),
                    "retryable": exc.retryable,
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return await known_error(
            request, ApiError("invalid_input", "Request does not match the API schema", 422)
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return await known_error(
            request,
            ApiError(
                "http_error", "This endpoint or media request is not available", exc.status_code
            ),
        )

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        log.error("Unhandled service error: %s", type(exc).__name__)
        return await known_error(
            request,
            ApiError("internal_error", "The service could not complete the request", 500, True),
        )

    @app.get("/health")
    async def health():
        return {"status": "alive", "service": name}

    return app


class BodyLimit:
    """Bound the raw transport body before multipart parsing, including chunked uploads."""

    def __init__(self, app, maximum):
        self.app, self.maximum = app, maximum

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        messages, length = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            length += len(message.get("body", b""))
            if length > self.maximum:
                response = JSONResponse(
                    status_code=413,
                    content={
                        "error": {
                            "code": "invalid_size",
                            "message": "Request body exceeds the transport limit",
                            "request_id": request_id.get(),
                            "retryable": False,
                        }
                    },
                )
                return await response(scope, receive, send)
            messages.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            if messages:
                return messages.pop(0)
            return await receive()

        await self.app(scope, replay, send)


class InferenceGate:
    """Bounded admitted work, serial inference, queue+execution wall-clock timeout."""

    def __init__(self, capacity: int, timeout: float):
        self.capacity, self.timeout = capacity, timeout
        self.pending = 0
        self.lock = asyncio.Lock()

    @asynccontextmanager
    async def slot(self):
        if self.pending >= self.capacity:
            raise ApiError("busy", "The inference queue is full", 503, True)
        self.pending += 1
        try:
            async with asyncio.timeout(self.timeout):
                async with self.lock:
                    yield
        except TimeoutError:
            raise ApiError("inference_timeout", "Inference timed out", 504, True) from None
        finally:
            self.pending -= 1
