"""Application errors and centralized handlers producing one consistent JSON shape."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for expected, user-facing errors."""

    status_code = 500
    error_code = "INTERNAL_ERROR"
    message = "Internal server error"
    custom_body: dict | None = None

    def __init__(self, message: str | None = None, *, error_code: str | None = None,
                 headers: dict[str, str] | None = None) -> None:
        self.message = message or self.message
        self.error_code = error_code or self.error_code
        self.headers = headers
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code, error_code, message = 400, "BAD_REQUEST", "Bad request"


class UnauthorizedError(AppError):
    status_code, error_code, message = 401, "NOT_AUTHENTICATED", "Not authenticated"

    def __init__(self, message: str | None = None, *, error_code: str | None = None) -> None:
        super().__init__(message, error_code=error_code, headers={"WWW-Authenticate": "Bearer"})


class TokenExpiredError(UnauthorizedError):
    error_code, message = "TOKEN_EXPIRED", "Token has expired"


class InvalidTokenError(UnauthorizedError):
    error_code, message = "INVALID_TOKEN", "Invalid token"


class ForbiddenError(AppError):
    status_code, error_code, message = 403, "FORBIDDEN", "You do not have permission to do this"


class AccessNotApprovedError(AppError):
    """Rejected when client's access_status is not active."""

    status_code = 403
    error_code = "ACCESS_NOT_APPROVED"
    message = "Access not approved"

    def __init__(self, message: str = "Access not approved") -> None:
        self.custom_body = {"detail": message, "code": "ACCESS_NOT_APPROVED"}
        super().__init__(message, error_code="ACCESS_NOT_APPROVED")


class PinWrongError(AppError):
    status_code = 400
    error_code = "PIN_WRONG"

    def __init__(self, tries_left: int) -> None:
        unit = "try" if tries_left == 1 else "tries"
        msg = f"Wrong PIN. {tries_left} {unit} left."
        self.custom_body = {
            "detail": msg,
            "code": "PIN_WRONG",
            "tries_left": tries_left,
        }
        super().__init__(msg, error_code="PIN_WRONG")


class PinLockedError(AppError):
    status_code = 400
    error_code = "PIN_LOCKED"

    def __init__(self, retry_after_seconds: int, message: str = "PIN locked. Please try again later.") -> None:
        self.custom_body = {
            "detail": message,
            "code": "PIN_LOCKED",
            "retry_after_seconds": retry_after_seconds,
        }
        super().__init__(message, error_code="PIN_LOCKED")


class EmailNotVerifiedError(AppError):
    status_code = 403
    error_code = "EMAIL_NOT_VERIFIED"
    message = "Email not verified"

    def __init__(self, message: str = "Email not verified") -> None:
        self.custom_body = {"detail": message, "code": "EMAIL_NOT_VERIFIED"}
        super().__init__(message, error_code="EMAIL_NOT_VERIFIED")


class PaymentNotAllowedError(AppError):
    status_code = 403
    error_code = "PAYMENT_NOT_ALLOWED"
    message = "Payment submission not allowed for current access status"

    def __init__(self, message: str = "Payment submission not allowed for current access status") -> None:
        self.custom_body = {"detail": message, "code": "PAYMENT_NOT_ALLOWED"}
        super().__init__(message, error_code="PAYMENT_NOT_ALLOWED")


class CodeCooldownError(AppError):
    status_code = 429
    error_code = "COOLDOWN_ACTIVE"
    message = "Please wait before requesting another code"

    def __init__(self, message: str = "Please wait before requesting another code") -> None:
        self.custom_body = {"detail": message, "code": "COOLDOWN_ACTIVE"}
        super().__init__(message, error_code="COOLDOWN_ACTIVE")


class CodeRateLimitError(AppError):
    status_code = 429
    error_code = "RATE_LIMIT_EXCEEDED"
    message = "Too many requests. Try again later."

    def __init__(self, message: str = "Too many requests. Try again later.") -> None:
        self.custom_body = {"detail": message, "code": "RATE_LIMIT_EXCEEDED"}
        super().__init__(message, error_code="RATE_LIMIT_EXCEEDED")


class CodeInvalidError(AppError):
    status_code = 400
    error_code = "CODE_INVALID"

    def __init__(self, tries_left: int) -> None:
        unit = "try" if tries_left == 1 else "tries"
        msg = f"Wrong verification code. {tries_left} {unit} left."
        self.custom_body = {
            "detail": msg,
            "code": "CODE_INVALID",
            "tries_left": tries_left,
        }
        super().__init__(msg, error_code="CODE_INVALID")


class CodeExpiredError(AppError):
    status_code = 400
    error_code = "CODE_EXPIRED"
    message = "Verification code has expired"

    def __init__(self, message: str = "Verification code has expired") -> None:
        self.custom_body = {"detail": message, "code": "CODE_EXPIRED"}
        super().__init__(message, error_code="CODE_EXPIRED")


class CodeAttemptsExceededError(AppError):
    status_code = 400
    error_code = "MAX_ATTEMPTS_EXCEEDED"
    message = "Too many failed attempts. Please request a new code."

    def __init__(self, message: str = "Too many failed attempts. Please request a new code.") -> None:
        self.custom_body = {"detail": message, "code": "MAX_ATTEMPTS_EXCEEDED"}
        super().__init__(message, error_code="MAX_ATTEMPTS_EXCEEDED")


class TransactionDuplicateError(AppError):
    status_code = 400
    error_code = "TRANSACTION_DUPLICATE"
    message = "Transaction ID already submitted"

    def __init__(self, message: str = "Transaction ID already submitted") -> None:
        self.custom_body = {
            "success": False,
            "message": message,
            "error_code": "TRANSACTION_DUPLICATE",
        }
        super().__init__(message, error_code="TRANSACTION_DUPLICATE")



class NotFoundError(AppError):
    status_code, error_code, message = 404, "NOT_FOUND", "Resource not found"


class UnprocessableError(AppError):
    """Well-formed request that breaks a business rule (e.g. a date in the past)."""

    status_code, error_code, message = 422, "UNPROCESSABLE", "Request cannot be processed"


class ConflictError(AppError):
    status_code, error_code, message = 409, "CONFLICT", "Resource already exists"


_STATUS_CODES = {
    400: "BAD_REQUEST", 401: "NOT_AUTHENTICATED", 403: "FORBIDDEN", 404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED", 409: "CONFLICT", 422: "VALIDATION_ERROR", 429: "RATE_LIMITED",
}


def _error_body(message: str, error_code: str, errors: list | None = None) -> dict:
    body: dict = {"success": False, "message": message, "error_code": error_code}
    if errors:
        body["errors"] = errors
    return body


async def _app_error(request: Request, exc: AppError) -> JSONResponse:
    _log_rejected(request, exc.status_code, exc.error_code, exc.message)
    if getattr(exc, "custom_body", None) is not None:
        return JSONResponse(exc.custom_body, exc.status_code, headers=exc.headers)
    return JSONResponse(_error_body(exc.message, exc.error_code), exc.status_code,
                        headers=exc.headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Only field + message are returned: never echo submitted values (may hold passwords).
    errors = [
        {"field": ".".join(str(p) for p in e["loc"] if p != "body"), "message": e["msg"]}
        for e in exc.errors()
    ]
    if getattr(request.state, "sarvam_tool_token_valid", False):
        try:
            from app.services.tool_call_log_service import log_tool_validation_failure
            log_tool_validation_failure(request)
        except Exception:
            logger.exception("Could not audit a validated Sarvam tool request failure")
    _log_rejected(request, 422, "VALIDATION_ERROR", errors, getattr(exc, "body", None))
    return JSONResponse(_error_body("Validation failed", "VALIDATION_ERROR", errors), 422)


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    if exc.status_code == 404 and "/webhooks/sarvam//" in request.url.path:
        try:
            from app.services.tool_call_log_service import log_invalid_tool_token
            log_invalid_tool_token(
                "missing_token", request_id=getattr(request.state, "request_id", None))
        except Exception:
            logger.exception("Could not log a tokenless Sarvam tool request")
    if isinstance(exc.detail, dict):
        return JSONResponse(exc.detail, exc.status_code, headers=getattr(exc, "headers", None))
    code = _STATUS_CODES.get(exc.status_code, "HTTP_ERROR")
    return JSONResponse(_error_body(str(exc.detail), code), exc.status_code,
                        headers=getattr(exc, "headers", None))


async def _rate_limited(_: Request, __: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(_error_body("Too many requests, please slow down", "RATE_LIMITED"), 429)


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    logger.error("Unhandled error [request_id=%s]", request_id, exc_info=exc)
    return JSONResponse(_error_body("Internal server error", "INTERNAL_ERROR"), 500)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RateLimitExceeded, _rate_limited)
    app.add_exception_handler(Exception, _unhandled)


def _log_rejected(request, status, code, detail, body=None):
    if status != 422:
        return
    import re
    path = re.sub(r"(/sarvam/)[^/]+", r"\1<token>", request.url.path)
    logger.warning("422 %s code=%s detail=%s body=%s", path, code, detail, None)
