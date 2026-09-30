from datetime import UTC, datetime

import pytest

from madmp_api.api.http import (
    JSON_MEDIA_TYPE,
    VENDOR_MEDIA_TYPE,
    http_date,
    negotiate_content_type,
    parse_http_date,
    require_supported_body,
)
from madmp_api.errors import NotAcceptableError, UnsupportedMediaTypeError


def test_negotiate_defaults_to_json():
    assert negotiate_content_type(None) == JSON_MEDIA_TYPE
    assert negotiate_content_type("*/*") == JSON_MEDIA_TYPE
    assert negotiate_content_type("application/json") == JSON_MEDIA_TYPE


def test_negotiate_prefers_vendor_type():
    accept = f"{VENDOR_MEDIA_TYPE}, application/json;q=0.9"
    assert negotiate_content_type(accept) == VENDOR_MEDIA_TYPE


def test_negotiate_rejects_unacceptable():
    with pytest.raises(NotAcceptableError):
        negotiate_content_type("text/html")


def test_require_supported_body():
    require_supported_body(None)
    require_supported_body("application/json; charset=utf-8")
    require_supported_body(VENDOR_MEDIA_TYPE)
    with pytest.raises(UnsupportedMediaTypeError):
        require_supported_body("text/plain")


def test_http_date_round_trip():
    value = datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC)
    parsed = parse_http_date(http_date(value))
    assert parsed == value


def test_parse_http_date_invalid():
    assert parse_http_date(None) is None
    assert parse_http_date("nonsense") is None
