"""Shared test constants and factories."""

WIZARD_BASE = "http://dsw.test/wizard-api"


def sample_dmp_document() -> dict:
    return {
        "dmp": {
            "title": "Test DMP",
            "description": "a description",
            "created": "2024-01-01T00:00:00+00:00",
            "modified": "2024-01-02T00:00:00+00:00",
            "language": "eng",
            "dmp_id": {"identifier": "doi:10.1/x", "type": "doi"},
            "contact": {
                "name": "Ada",
                "mbox": "ada@example.org",
                "contact_id": {
                    "identifier": "0000-0001",
                    "type": "orcid",
                },
            },
            "dataset": [
                {
                    "title": "Dataset A",
                    "dataset_id": {"identifier": "ds-a", "type": "url"},
                    "personal_data": "no",
                    "sensitive_data": "no",
                },
            ],
            "ethical_issues_exist": "no",
        },
    }
