"""Structured query parameters for the maDMP list endpoint.

Kept dependency-free (no API or ORM imports) so both the API layer
(which builds it) and the repository (which consumes it) can share it.
"""

from dataclasses import dataclass, field
from datetime import datetime

SORT_FIELDS = ('title', 'created', 'modified', 'language')

# ListParams field name == MadmpRow column name, so the repository can
# iterate these generically for array-overlap filters.
ARRAY_FILTER_FIELDS = (
    'dataset_ids',
    'contributor_ids',
    'contact_ids',
    'dmp_ids',
    'dmp_alternate_identifiers',
    'host_ids',
    'funder_ids',
    'grant_ids',
    'metadata_standard_ids',
    'license_refs',
    'distribution_formats',
    'distribution_data_access',
    'funding_status',
    'dataset_personal_data',
    'dataset_sensitive_data',
)


def _default_sort() -> list[tuple[str, str]]:
    return [('created', 'desc')]


@dataclass
class ListParams:
    offset: int = 0
    count: int = 20
    sort: list[tuple[str, str]] = field(default_factory=_default_sort)

    # Authorisation restriction: only these ids may appear in results.
    allowed_ids: set[str] | None = None

    created_before: datetime | None = None
    created_after: datetime | None = None
    modified_before: datetime | None = None
    modified_after: datetime | None = None
    languages: list[str] | None = None
    query: list[str] | None = None
    ethical_issues_exist: list[str] | None = None

    dataset_ids: list[str] | None = None
    contributor_ids: list[str] | None = None
    contact_ids: list[str] | None = None
    dmp_ids: list[str] | None = None
    dmp_alternate_identifiers: list[str] | None = None
    host_ids: list[str] | None = None
    funder_ids: list[str] | None = None
    grant_ids: list[str] | None = None
    metadata_standard_ids: list[str] | None = None
    license_refs: list[str] | None = None
    distribution_formats: list[str] | None = None
    distribution_data_access: list[str] | None = None
    funding_status: list[str] | None = None
    dataset_personal_data: list[str] | None = None
    dataset_sensitive_data: list[str] | None = None
