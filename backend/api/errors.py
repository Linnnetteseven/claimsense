"""
One error shape for every endpoint:

    {"error": {"code": "not_found", "message": "Claim 'X' not found", "details": null}}

Raise ApiError in route code. HTTPException, request validation errors and
unexpected exceptions are converted to the same shape by the handlers below;
unexpected errors never leak internals (they are logged instead).
"""

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("hakiki.errors")

_CODES = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
    409: "conflict", 422: "invalid_request", 502: "upstream_error", 503: "unavailable",
}


class ApiError(Exception):
    def __init__(self, status: int, message: str, code: Optional[str] = None, details: Any = None):
        super().__init__(message)
        self.status, self.message, self.details = status, message, details
        self.code = code or _CODES.get(status, "error")


def error_body(code: str, message: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(error_body(exc.code, exc.message, exc.details), status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse(
            error_body(_CODES.get(exc.status_code, "error"), str(exc.detail)), status_code=exc.status_code
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse(error_body("invalid_request", "The request is not valid", details), status_code=422)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(error_body("internal_error", "Something went wrong on the server"), status_code=500)
