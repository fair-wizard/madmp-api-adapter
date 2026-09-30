import pytest
from starlette.datastructures import QueryParams

from madmp_api.api.params import parse_list_params
from madmp_api.errors import InvalidQueryStringError


def _params(query: str) -> QueryParams:
    return QueryParams(query)


def test_defaults():
    p = parse_list_params(_params(""))
    assert p.offset == 0
    assert p.count == 20
    assert p.sort == [("created", "desc")]


def test_array_params_both_conventions():
    p = parse_list_params(
        _params("dataset_ids=a&dataset_ids[]=b&funder_ids[]=f"),
    )
    assert set(p.dataset_ids or []) == {"a", "b"}
    assert p.funder_ids == ["f"]


def test_dmp_alternate_identifier_maps_to_plural_field():
    p = parse_list_params(_params("dmp_alternate_identifier[]=alt1"))
    assert p.dmp_alternate_identifiers == ["alt1"]


def test_sort_parsing():
    p = parse_list_params(_params("sort[]=title,asc&sort[]=modified,desc"))
    assert p.sort == [("title", "asc"), ("modified", "desc")]


@pytest.mark.parametrize(
    "query",
    [
        "count=0",
        "count=101",
        "offset=-1",
        "count=abc",
        "sort[]=title,sideways",
        "sort[]=unknown,asc",
        "created_before=not-a-date",
    ],
)
def test_invalid_params_rejected(query: str):
    with pytest.raises(InvalidQueryStringError):
        parse_list_params(_params(query))


def test_count_cap_boundaries_ok():
    assert parse_list_params(_params("count=1")).count == 1
    assert parse_list_params(_params("count=100")).count == 100
