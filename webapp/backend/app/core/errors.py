"""Unified error envelope and domain-error mapping."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .context import get_request_id

logger = logging.getLogger("hydro.web.errors")

REQUEST_ID_HEADER = "X-Request-ID"
SESSION_HEADER = "X-Session-ID"


class AppError(Exception):
    """An error that is safe to return to the client as an envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def envelope(self, request_id: str | None = None) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "request_id": request_id or get_request_id(),
        }


def not_found(resource: str, resource_id: str | None = None) -> AppError:
    return AppError(
        "not_found",
        f"Kaynak bulunamadi: {resource}.",
        status_code=404,
        details={"resource": resource, "id": resource_id},
    )


def validation_error(message: str, *, field: str | None = None) -> AppError:
    details: dict[str, Any] = {}
    if field:
        details["field"] = field
    return AppError("validation_error", message, status_code=422, details=details)


def domain_error(status_code: int, code: str, message: str, **details: Any) -> AppError:
    return AppError(code, message, status_code=status_code, details=details)


def error_from_domain(exc: BaseException, *, reference_table_hint: bool = False) -> AppError:
    """Translate a ``hidrostatik_test`` exception into an :class:`AppError`.

    ``reference_table_hint`` lets table-backed coefficient endpoints classify
    out-of-range table lookups separately (the domain wraps some table errors
    inside ``ValidationError``).
    """

    from hidrostatik_test.data.ab_control_table import ABControlTableError
    from hidrostatik_test.domain import ValidationError as DomainValidationError
    from hidrostatik_test.domain.water_properties import WaterPropertyError

    message = str(exc)
    if isinstance(exc, ABControlTableError):
        return domain_error(
            400,
            "reference_table_error",
            message or "Referans tablosu araligi disinda.",
        )
    if isinstance(exc, WaterPropertyError):
        return domain_error(400, "water_property_error", message)
    if isinstance(exc, DomainValidationError):
        if reference_table_hint and _looks_like_table_range(message):
            return domain_error(400, "reference_table_error", message)
        return domain_error(400, "domain_validation_error", message)
    return AppError("internal_error", "Beklenmeyen bir hata olustu.", status_code=500)


def _looks_like_table_range(message: str) -> bool:
    lowered = message.lower()
    return "aralik disi" in lowered or "kontrol tablosu" in lowered


def _jsonable_validation_errors(errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for error in errors:
        item: dict[str, Any] = {
            "loc": list(error.get("loc", [])),
            "msg": str(error.get("msg", "")),
            "type": str(error.get("type", "")),
        }
        if "input" in error:
            item["input"] = _safe_value(error.get("input"))
        cleaned.append(item)
    return cleaned


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    return str(value)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(request: Request, exc: AppError) -> JSONResponse:  # noqa: ARG001
        return JSONResponse(
            status_code=exc.status_code,
            content=exc.envelope(getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        error = AppError(
            "validation_error",
            "Girdi dogrulanamadi.",
            status_code=422,
            details={"errors": _jsonable_validation_errors(list(exc.errors()))},
        )
        return JSONResponse(
            status_code=422,
            content=error.envelope(getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            404: "not_found",
            405: "method_not_allowed",
            413: "file_too_large",
            415: "unsupported_format",
        }.get(exc.status_code, "http_error")
        message = str(exc.detail or "Istek tamamlanamadi.")
        error = AppError(code, message, status_code=exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content=error.envelope(getattr(request.state, "request_id", None)),
        )

    @app.exception_handler(Exception)
    async def _unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        logger.exception("Unhandled error request_id=%s route=%s", request_id, request.url.path)
        error = AppError(
            "internal_error",
            "Beklenmeyen bir hata olustu.",
            status_code=500,
        )
        return JSONResponse(status_code=500, content=error.envelope(request_id))


__all__ = [
    "AppError",
    "REQUEST_ID_HEADER",
    "SESSION_HEADER",
    "domain_error",
    "error_from_domain",
    "not_found",
    "register_exception_handlers",
    "validation_error",
]
