"""Pydantic models for the RDA DMP Common Standard (maDMP) v1.2.

Curated by hand from the RDA-DMP-Common ``common-madmp-api`` OpenAPI
spec. Field names match the JSON keys exactly (snake_case), so no aliases
are needed. Large ISO enumerations (language, country, currency, PID
system, certification) are modelled as plain strings to stay lenient with
real-world inputs; only the small closed vocabularies used by the RDA list
filters are modelled as enums.
"""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class Booleanish(StrEnum):
    YES = 'yes'
    NO = 'no'
    UNKNOWN = 'unknown'


class DataAccess(StrEnum):
    OPEN = 'open'
    SHARED = 'shared'
    CLOSED = 'closed'


class FundingStatus(StrEnum):
    PLANNED = 'planned'
    APPLIED = 'applied'
    GRANTED = 'granted'
    REJECTED = 'rejected'


class _Base(BaseModel):
    # Extensions must be additive per the spec; keep unknown fields so the
    # maDMP round-trips through the store without data loss.
    model_config = ConfigDict(extra='allow')


class Identifier(_Base):
    identifier: str
    type: str


class RelatedIdentifier(_Base):
    identifier: str
    type: str
    relation_type: str
    metadata_scheme: str | None = None
    resource_type: str | None = None
    scheme_type: str | None = None
    scheme_uri: str | None = None


class Affiliation(_Base):
    name: str
    affiliation_id: Identifier


class Contact(_Base):
    name: str
    mbox: str
    contact_id: Identifier | list[Identifier]
    affiliation: list[Affiliation] | None = None


class Contributor(_Base):
    name: str
    role: list[str]
    contributor_id: Identifier | list[Identifier]
    mbox: str | None = None
    affiliation: list[Affiliation] | None = None


class Creator(_Base):
    name: str
    creator_id: Identifier | list[Identifier]


class License(_Base):
    license_ref: str
    start_date: date


class Host(_Base):
    title: str
    url: str
    description: str | None = None
    availability: str | None = None
    backup_frequency: str | None = None
    backup_type: str | None = None
    storage_type: str | None = None
    certified_with: str | None = None
    geo_location: str | None = None
    pid_system: list[str] | None = None
    support_versioning: Booleanish | None = None
    host_id: list[Identifier] | None = None


class Distribution(_Base):
    title: str
    data_access: DataAccess
    description: str | None = None
    access_url: str | None = None
    download_url: str | None = None
    available_until: date | None = None
    issued: date | None = None
    byte_size: int | None = None
    format: list[str] | None = None
    host: Host | None = None
    license: list[License] | None = None


class Metadata(_Base):
    language: str
    metadata_standard_id: Identifier | list[Identifier]
    description: str | None = None


class SecurityAndPrivacyItem(_Base):
    title: str
    description: str | None = None


class TechnicalResource(_Base):
    name: str
    description: str | None = None
    technical_resource_id: list[Identifier] | None = None


class Dataset(_Base):
    title: str
    dataset_id: Identifier
    personal_data: Booleanish
    sensitive_data: Booleanish
    description: str | None = None
    type: str | None = None
    language: str | None = None
    issued: date | None = None
    is_reused: bool | None = None
    keyword: list[str] | None = None
    rights: str | None = None
    preservation_statement: str | None = None
    data_quality_assurance: list[str] | None = None
    creator: list[Creator] | None = None
    distribution: list[Distribution] | None = None
    metadata: list[Metadata] | None = None
    security_and_privacy: list[SecurityAndPrivacyItem] | None = None
    technical_resource: list[TechnicalResource] | None = None
    alternate_identifier: list[Identifier] | None = None
    related_identifier: list[RelatedIdentifier] | None = None


class Funding(_Base):
    funder_id: Identifier
    grant_id: Identifier | None = None
    funding_status: FundingStatus | None = None


class Project(_Base):
    title: str
    description: str | None = None
    start: date | None = None
    end: date | None = None
    project_id: list[Identifier] | None = None
    funding: list[Funding] | None = None


class Cost(_Base):
    title: str
    description: str | None = None
    value: float | None = None
    currency_code: str | None = None


class DMPData(_Base):
    title: str
    created: datetime
    modified: datetime
    language: str
    dmp_id: Identifier
    contact: Contact
    dataset: list[Dataset]
    ethical_issues_exist: Booleanish
    description: str | None = None
    contributor: list[Contributor] | None = None
    project: list[Project] | None = None
    cost: list[Cost] | None = None
    ethical_issues_description: str | None = None
    ethical_issues_report: str | None = None
    alternate_identifier: list[Identifier] | None = None
    related_identifier: list[RelatedIdentifier] | None = None


class DMPDocument(_Base):
    dmp: DMPData


class DMPWithID(_Base):
    id: str
    dmp: DMPData
