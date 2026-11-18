from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from occupational_health.core.logging import request_id_context

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        data: Any = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.data = data
        self.retry_after = retry_after


def request_id() -> str:
    return request_id_context.get() or str(uuid4())


def envelope(code: str, message: str, data: Any = None) -> dict:
    return {
        "code": code,
        "message": message,
        "data": jsonable_encoder(data),
        "request_id": request_id(),
    }


def success(data: Any = None, message: str = "success") -> dict:
    return envelope("OK", message, data)


def error_response(error: ApiError) -> JSONResponse:
    headers = None
    if error.retry_after is not None:
        headers = {"Retry-After": str(max(1, int(error.retry_after)))}
    return JSONResponse(
        status_code=error.status_code,
        content=envelope(error.code, error.message, error.data),
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def handle_validation(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {"location": [str(part) for part in item["loc"]], "message": item["msg"]}
            for item in exc.errors()
        ]
        return error_response(
            ApiError(400, "VALIDATION_ERROR", "请求参数不符合要求", details)
        )

    @app.exception_handler(HTTPException)
    async def handle_http(_request: Request, exc: HTTPException) -> JSONResponse:
        codes = {
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            429: "RATE_LIMITED",
        }
        code = codes.get(
            exc.status_code,
            "VALIDATION_ERROR" if exc.status_code < 500 else "INTERNAL_ERROR",
        )
        message = str(exc.detail) if exc.status_code < 500 else "服务暂时不可用"
        return error_response(ApiError(exc.status_code, code, message))

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled request failure", exc_info=type(exc))
        return error_response(
            ApiError(500, "INTERNAL_ERROR", "服务处理失败，请凭请求编号联系管理员")
        )
