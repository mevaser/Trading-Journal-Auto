from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    RESOURCE_NOT_FOUND = "resource_not_found"
    DOMAIN_VALIDATION = "domain_validation"
    REQUEST_VALIDATION = "request_validation"
    AUTH_UNAUTHORIZED = "auth_unauthorized"
    AUTH_FORBIDDEN = "auth_forbidden"
    INTERNAL_ERROR = "internal_error"


class AppError(Exception):
    def __init__(self, *, code: ErrorCode, message: str, status_code: int, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


class ResourceNotFoundError(AppError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            code=ErrorCode.RESOURCE_NOT_FOUND,
            message=message,
            status_code=404,
            details=details,
        )


class DomainValidationError(AppError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            code=ErrorCode.DOMAIN_VALIDATION,
            message=message,
            status_code=400,
            details=details,
        )


class AuthenticationRequiredError(AppError):
    def __init__(self, message: str = "Authentication required", details: dict | None = None):
        super().__init__(
            code=ErrorCode.AUTH_UNAUTHORIZED,
            message=message,
            status_code=401,
            details=details,
        )


class AuthorizationDeniedError(AppError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            code=ErrorCode.AUTH_FORBIDDEN,
            message=message,
            status_code=403,
            details=details,
        )
