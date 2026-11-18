"""Exception handlers. Internal details never reach the client."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError, ValidationAppError

logger = logging.getLogger(__name__)

_HUMAN_MESSAGES = {
    "Field required": "Обязательное поле.",
    "Input should be a valid integer": "Ожидается целое число.",
    "Input should be a valid string": "Ожидается текст.",
    "Input should be a valid decimal": "Ожидается число.",
    "Input should be greater than or equal to 0": "Значение не может быть отрицательным.",
    "String should have at least 2 characters": "Слишком короткое значение.",
    "String should have at most 120 characters": "Слишком длинное значение.",
    "Extra inputs are not permitted": "Неизвестное поле.",
    "Input should be 'sell' or 'buy'": "Тип объявления должен быть «Продам» или «Куплю».",
}


def _humanize_message(error: dict) -> str:
    message = str(error.get("msg", "Некорректное значение."))
    message = message.removeprefix("Value error, ").strip()
    return _HUMAN_MESSAGES.get(message, message)


def _field_path(error: dict) -> str:
    parts = [str(part) for part in error.get("loc", ())]
    while parts and parts[0] in {"body", "query", "path", "header"}:
        parts.pop(0)
    return ".".join(parts) or "body"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("Application error on %s %s: %s", request.method, request.url.path, exc.code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers=exc.headers or None,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        fields = [
            {"field": _field_path(error), "message": _humanize_message(error)}
            for error in exc.errors()
        ]
        payload = ValidationAppError()
        return JSONResponse(
            status_code=payload.status_code,
            content={
                "error": {"code": payload.code, "message": payload.message},
                "fields": fields,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if not request.url.path.startswith("/api"):
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        message = exc.detail if isinstance(exc.detail, str) else "Запрос не может быть обработан."
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": "http_error", "message": message}},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Внутренняя ошибка сервера. Попробуйте позже.",
                }
            },
        )
