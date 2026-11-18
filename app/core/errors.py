"""Application level errors that are safe to expose to API clients."""

from __future__ import annotations

from collections.abc import Mapping


class AppError(Exception):
    """Base class for expected errors.

    The response never contains a traceback: only `code` and `message` are
    returned to the client. Internal details go to the server log only.
    """

    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "Внутренняя ошибка сервера."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.code = code or self.code
        self.headers = dict(headers or {})
        super().__init__(self.message)


class AuthenticationError(AppError):
    status_code = 401
    code = "unauthorized"
    default_message = "Не удалось подтвердить вход через Telegram. Откройте приложение из бота."


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "Недостаточно прав для этого действия."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    default_message = "Объявление не найдено."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    default_message = "Действие конфликтует с текущим состоянием."


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"
    default_message = "Файл слишком большой."


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Слишком много запросов. Попробуйте немного позже."


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"
    default_message = "Проверьте правильность заполнения полей."
