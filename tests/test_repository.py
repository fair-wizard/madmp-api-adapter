from datetime import UTC, datetime

import pytest

from madmp_api.madmp.models import DMPData
from madmp_api.store import repository
from madmp_api.store.query import ListParams
from tests.conftest import ROWS

pytestmark = pytest.mark.asyncio


def _dmp(
    *,
    title: str = "T",
    created: str = "2024-01-01T00:00:00+00:00",
    funder: str | None = None,
    dataset_id: str = "ds-1",
) -> DMPData:
    project = (
        [
            {
                "title": "P",
                "funding": [
                    {"funder_id": {"identifier": funder, "type": "url"}},
                ],
            },
        ]
        if funder
        else None
    )
    return DMPData.model_validate(
        {
            "title": title,
            "description": f"about {title}",
            "created": created,
            "modified": "2024-06-01T00:00:00+00:00",
            "language": "eng",
            "dmp_id": {"identifier": f"id-{title}", "type": "url"},
            "contact": {
                "name": "C",
                "mbox": "c@x.y",
                "contact_id": {"identifier": "c", "type": "other"},
            },
            "dataset": [
                {
                    "title": f"Dataset {title}",
                    "dataset_id": {"identifier": dataset_id, "type": "url"},
                    "personal_data": "no",
                    "sensitive_data": "no",
                },
            ],
            "ethical_issues_exist": "no",
            "project": project,
        },
    )


async def _seed(session, dmp_id, dmp):
    await repository.upsert(
        session,
        ROWS,
        tenant="",
        dmp_id=dmp_id,
        dmp=dmp,
        id_base_url="http://test/dmps",
        wizard_project_uuid=dmp_id,
        wizard_updated_at=datetime(2024, 6, 1, tzinfo=UTC),
    )


async def test_upsert_and_get(db_session):
    await _seed(db_session, "p1", _dmp(title="Alpha"))
    row = await repository.get(db_session, ROWS, "", "p1")
    assert row is not None
    assert row.data["title"] == "Alpha"
    assert row.dataset_ids == ["ds-1"]


async def test_upsert_is_idempotent(db_session):
    await _seed(db_session, "p1", _dmp(title="One"))
    await _seed(db_session, "p1", _dmp(title="Two"))
    total, rows = await repository.query(db_session, ROWS, "", ListParams())
    assert total == 1
    assert rows[0].data["title"] == "Two"


async def test_pagination_and_total(db_session):
    for i in range(5):
        await _seed(db_session, f"p{i}", _dmp(title=f"T{i}"))
    total, rows = await repository.query(
        db_session,
        ROWS,
        "",
        ListParams(offset=0, count=2),
    )
    assert total == 5
    assert len(rows) == 2


async def test_sort_by_title_asc(db_session):
    await _seed(db_session, "b", _dmp(title="Bravo"))
    await _seed(db_session, "a", _dmp(title="Alpha"))
    _total, rows = await repository.query(
        db_session,
        ROWS,
        "",
        ListParams(sort=[("title", "asc")]),
    )
    assert [r.data["title"] for r in rows] == ["Alpha", "Bravo"]


async def test_filter_funder_ids(db_session):
    await _seed(db_session, "p1", _dmp(title="A", funder="funder:1"))
    await _seed(db_session, "p2", _dmp(title="B", funder="funder:2"))
    _total, rows = await repository.query(
        db_session,
        ROWS,
        "",
        ListParams(funder_ids=["funder:1"]),
    )
    assert {r.id for r in rows} == {"p1"}


async def test_free_text_query(db_session):
    await _seed(db_session, "p1", _dmp(title="Genomics"))
    await _seed(db_session, "p2", _dmp(title="Astronomy"))
    _total, rows = await repository.query(
        db_session,
        ROWS,
        "",
        ListParams(query=["genomics"]),
    )
    assert {r.id for r in rows} == {"p1"}


async def test_allowed_ids_restricts_results(db_session):
    await _seed(db_session, "p1", _dmp(title="A"))
    await _seed(db_session, "p2", _dmp(title="B"))
    total, rows = await repository.query(
        db_session,
        ROWS,
        "",
        ListParams(allowed_ids={"p1"}),
    )
    assert total == 1
    assert rows[0].id == "p1"
