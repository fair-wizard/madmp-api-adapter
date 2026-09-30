"""Adapter-wide error hierarchy mapped to RDA maDMP error responses.

Each error carries the HTTP ``status`` and the RDA ``error_code`` constant
required by the common-madmp-api spec. The API layer renders these as
``{error_code, error_message}`` bodies.
"""

from http import HTTPStatus
from typing import ClassVar


class AdapterError(Exception):
    status: ClassVar[HTTPStatus] = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code: ClassVar[str] = 'generic_error'

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.error_code)
        self.error_message = message or self.error_code


class BadRequestError(AdapterError):
    status = HTTPStatus.BAD_REQUEST
    error_code = 'bad_request'


class InvalidQueryStringError(BadRequestError):
    error_code = 'invalid_query_string'


class DMPInvalidError(BadRequestError):
    error_code = 'dmp_invalid'


class AuthenticationRequiredError(AdapterError):
    status = HTTPStatus.UNAUTHORIZED
    error_code = 'authentication_required'


class InsufficientPermissionsError(AdapterError):
    status = HTTPStatus.FORBIDDEN
    error_code = 'insufficient_permissions'


class DMPNotFoundError(AdapterError):
    status = HTTPStatus.NOT_FOUND
    error_code = 'dmp_not_found'


class TenantNotFoundError(AdapterError):
    """The request host is not one this adapter serves a Wizard API for."""

    status = HTTPStatus.NOT_FOUND
    error_code = 'generic_error'

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or 'no Wizard API is served on this host')


class NotAcceptableError(AdapterError):
    status = HTTPStatus.NOT_ACCEPTABLE
    error_code = 'not_acceptable'


class ConflictError(AdapterError):
    status = HTTPStatus.CONFLICT
    error_code = 'conflict'


class UnsupportedMediaTypeError(AdapterError):
    status = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    error_code = 'unsupported_media_type'


class UpstreamError(AdapterError):
    """Wizard returned an unexpected error we cannot translate precisely."""

    status = HTTPStatus.BAD_GATEWAY
    error_code = 'generic_error'
