"""Content negotiation and HTTP date helpers for the RDA maDMP API."""

from datetime import datetime
from email.utils import format_datetime, parsedate_to_datetime

from madmp_api.errors import NotAcceptableError, UnsupportedMediaTypeError

JSON_MEDIA_TYPE = 'application/json'
VENDOR_MEDIA_TYPE = 'application/vnd.org.rd-alliance.dmp-common.v1.2+json'
_ACCEPTABLE_BODY = frozenset({JSON_MEDIA_TYPE, VENDOR_MEDIA_TYPE})
_WILDCARDS = frozenset({'*/*', 'application/*', JSON_MEDIA_TYPE})


def negotiate_content_type(accept: str | None) -> str:
    if not accept:
        return JSON_MEDIA_TYPE
    media = [part.split(';')[0].strip() for part in accept.split(',')]
    if VENDOR_MEDIA_TYPE in media:
        return VENDOR_MEDIA_TYPE
    if any(item in _WILDCARDS for item in media):
        return JSON_MEDIA_TYPE
    msg = 'no acceptable representation for the Accept header'
    raise NotAcceptableError(msg)


def require_supported_body(content_type: str | None) -> None:
    if content_type is None:
        return
    media = content_type.split(';')[0].strip()
    if media and media not in _ACCEPTABLE_BODY:
        msg = f'unsupported request content type: {media}'
        raise UnsupportedMediaTypeError(msg)


def http_date(value: datetime) -> str:
    return format_datetime(value, usegmt=True)


def parse_http_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
