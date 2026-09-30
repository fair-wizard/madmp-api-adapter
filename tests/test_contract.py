"""Validate our maDMP output against the RDA common-madmp-api schema."""

from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from madmp_api.madmp.models import DMPData

_SPEC_PATH = Path(__file__).parent / "data" / "madmp-openapi.yaml"


@pytest.fixture(scope="session")
def validator_for():
    spec = yaml.safe_load(_SPEC_PATH.read_text())
    resource = Resource.from_contents(
        spec,
        default_specification=DRAFT202012,
    )
    registry = Registry().with_resource("urn:spec", resource)

    def _build(schema_name: str):
        ref = {"$ref": f"urn:spec#/components/schemas/{schema_name}"}
        return Draft202012Validator(ref, registry=registry)

    return _build


def test_sample_document_matches_schema(validator_for, make_document):
    validator_for("DMPDocument").validate(make_document())


def test_model_output_matches_schema(validator_for, make_document):
    # Round-trip a document through our pydantic model, then validate the
    # serialised form against the RDA DMPDocument schema.
    dmp = DMPData.model_validate(make_document()["dmp"])
    payload = {"dmp": dmp.model_dump(mode="json", exclude_none=True)}
    validator_for("DMPDocument").validate(payload)


def test_missing_required_field_fails_schema(validator_for, make_document):
    doc = make_document()
    del doc["dmp"]["contact"]
    validator = validator_for("DMPDocument")
    assert not validator.is_valid(doc)
