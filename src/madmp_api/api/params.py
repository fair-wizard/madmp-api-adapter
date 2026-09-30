"""Parse and validate RDA ``GET /dmps`` query parameters into ListParams.

Array parameters are accepted both as ``name=`` (repeated) and as the
RDA ``name[]=`` convention. Invalid input raises InvalidQueryStringError
(rendered as 400).
"""

from datetime import datetime

from starlette.datastructures import QueryParams

from madmp_api.errors import InvalidQueryStringError
from madmp_api.store.query import SORT_FIELDS, ListParams

_MAX_COUNT = 100
_DEFAULT_COUNT = 20
_SORT_DIRECTIONS = ('asc', 'desc')


def _getlist(qp: QueryParams, name: str) -> list[str]:
    return [*qp.getlist(name), *qp.getlist(f'{name}[]')]


def _first(qp: QueryParams, name: str) -> str | None:
    values = _getlist(qp, name)
    return values[0] if values else None


def _opt(values: list[str]) -> list[str] | None:
    return values or None


def _int(value: str | None, default: int, field: str) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        msg = f'{field} must be an integer'
        raise InvalidQueryStringError(msg) from exc


def _dt(qp: QueryParams, name: str) -> datetime | None:
    raw = _first(qp, name)
    if raw is None:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        msg = f'{name} must be an ISO 8601 date-time'
        raise InvalidQueryStringError(msg) from exc


def _sort(qp: QueryParams) -> list[tuple[str, str]]:
    raw = _getlist(qp, 'sort')
    if not raw:
        return [('created', 'desc')]
    result: list[tuple[str, str]] = []
    for item in raw:
        field, _, direction = item.partition(',')
        if field not in SORT_FIELDS or direction not in _SORT_DIRECTIONS:
            msg = f'invalid sort value: {item}'
            raise InvalidQueryStringError(msg)
        result.append((field, direction))
    return result


def _pagination(qp: QueryParams) -> tuple[int, int]:
    offset = _int(_first(qp, 'offset'), 0, 'offset')
    count = _int(_first(qp, 'count'), _DEFAULT_COUNT, 'count')
    if offset < 0:
        msg = 'offset must be >= 0'
        raise InvalidQueryStringError(msg)
    if not 1 <= count <= _MAX_COUNT:
        msg = f'count must be between 1 and {_MAX_COUNT}'
        raise InvalidQueryStringError(msg)
    return offset, count


def parse_list_params(qp: QueryParams) -> ListParams:
    offset, count = _pagination(qp)
    return ListParams(
        offset=offset,
        count=count,
        sort=_sort(qp),
        created_before=_dt(qp, 'created_before'),
        created_after=_dt(qp, 'created_after'),
        modified_before=_dt(qp, 'modified_before'),
        modified_after=_dt(qp, 'modified_after'),
        languages=_opt(_getlist(qp, 'languages')),
        query=_opt(_getlist(qp, 'query')),
        ethical_issues_exist=_opt(_getlist(qp, 'ethical_issues_exist')),
        dataset_ids=_opt(_getlist(qp, 'dataset_ids')),
        contributor_ids=_opt(_getlist(qp, 'contributor_ids')),
        contact_ids=_opt(_getlist(qp, 'contact_ids')),
        dmp_ids=_opt(_getlist(qp, 'dmp_ids')),
        dmp_alternate_identifiers=_opt(
            _getlist(qp, 'dmp_alternate_identifier'),
        ),
        host_ids=_opt(_getlist(qp, 'host_ids')),
        funder_ids=_opt(_getlist(qp, 'funder_ids')),
        grant_ids=_opt(_getlist(qp, 'grant_ids')),
        metadata_standard_ids=_opt(_getlist(qp, 'metadata_standard_ids')),
        license_refs=_opt(_getlist(qp, 'license_refs')),
        distribution_formats=_opt(_getlist(qp, 'distribution_formats')),
        distribution_data_access=_opt(
            _getlist(qp, 'distribution_data_access'),
        ),
        funding_status=_opt(_getlist(qp, 'funding_status')),
        dataset_personal_data=_opt(_getlist(qp, 'dataset_personal_data')),
        dataset_sensitive_data=_opt(
            _getlist(qp, 'dataset_sensitive_data'),
        ),
    )
