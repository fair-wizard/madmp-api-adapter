"""Map adapter + validation errors to RDA ``{error_code, error_message}``."""

from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from madmp_api.errors import AdapterError


def _body(code: str, message: str) -> dict[str, str]:
    return {'error_code': code, 'error_message': message}


def _adapter_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    if isinstance(exc, AdapterError):
        return JSONResponse(
            status_code=int(exc.status),
            content=_body(exc.error_code, exc.error_message),
        )
    return JSONResponse(
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        content=_body('generic_error', 'internal server error'),
    )


def _validation_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    _ = exc
    return JSONResponse(
        status_code=HTTPStatus.BAD_REQUEST,
        content=_body('dmp_invalid', 'request body failed validation'),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AdapterError, _adapter_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
