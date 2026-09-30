from datetime import UTC, datetime

from madmp_api.madmp.models import Booleanish, DMPData
from madmp_api.transform import dsw_root as km
from madmp_api.transform import replies as r
from madmp_api.transform.profiles import (
    DSWRootProfile,
    MappingProfile,
    ProjectContext,
    get_profile,
)
from tests.helpers import sample_dmp_document


def _ctx(replies: dict | None = None) -> ProjectContext:
    return ProjectContext(
        uuid="proj-1",
        settings={"name": "My Project", "description": "desc"},
        questionnaire={"replies": replies or {}},
        user={"uuid": "u1", "firstName": "Ada", "lastName": "Lovelace",
              "email": "ada@example.org"},
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        updated_at=datetime(2024, 6, 1, tzinfo=UTC),
    )


def _reply(value: dict) -> dict:
    return {"value": value, "createdAt": "2024-06-01T00:00:00+00:00"}


def test_base_profile_produces_required_fields():
    dmp = MappingProfile().to_dmp(_ctx())
    assert isinstance(dmp, DMPData)
    assert dmp.title == "My Project"
    assert dmp.language == "eng"
    assert dmp.dmp_id.identifier.endswith("/proj-1")
    # Wizard users expose firstName/lastName rather than a single name.
    assert dmp.contact.name == "Ada Lovelace"
    assert dmp.contact.mbox == "ada@example.org"
    assert dmp.ethical_issues_exist == Booleanish.UNKNOWN
    # At least one dataset is always synthesised (required by RDA).
    assert len(dmp.dataset) == 1


def test_profile_selection_by_km_id():
    assert isinstance(get_profile("dsw:root:2.7.0"), DSWRootProfile)
    assert not isinstance(get_profile("other:km:1.0.0"), DSWRootProfile)
    assert not isinstance(get_profile(None), DSWRootProfile)


def test_dsw_root_reads_datasets_and_ethical_issues():
    item = "item-1"
    id_item = "id-1"
    ds_list = r.path(km.CH_PRESERVE, km.Q_DATASETS)
    base = r.path(ds_list, item)
    id_list = r.path(base, km.Q_DS_IDENTIFIERS)
    id_base = r.path(id_list, id_item)
    replies = {
        ds_list: _reply({"type": "ItemListReply", "value": [item]}),
        r.path(base, km.Q_DS_TITLE): _reply(
            {"type": "StringReply", "value": "Genomics dataset"},
        ),
        r.path(base, km.Q_DS_DESCRIPTION): _reply(
            {"type": "StringReply", "value": "Sequencing reads"},
        ),
        r.path(base, km.Q_DS_PERSONAL): _reply(
            {"type": "AnswerReply", "value": km.A_PERSONAL_YES},
        ),
        r.path(base, km.Q_DS_SENSITIVE): _reply(
            {"type": "AnswerReply", "value": km.A_SENSITIVE_NO},
        ),
        id_list: _reply({"type": "ItemListReply", "value": [id_item]}),
        r.path(id_base, km.Q_DS_ID_VALUE): _reply(
            {"type": "StringReply", "value": "10.1234/abc"},
        ),
        r.path(id_base, km.Q_DS_ID_TYPE): _reply(
            {"type": "AnswerReply",
             "value": km.ID_TYPE_TO_ANSWER["doi"]},
        ),
        r.path(km.CH_COLLECT, km.Q_ETHICAL): _reply(
            {"type": "AnswerReply", "value": km.A_ETHICAL_YES},
        ),
    }
    dmp = DSWRootProfile().to_dmp(_ctx(replies))

    assert len(dmp.dataset) == 1
    dataset = dmp.dataset[0]
    assert dataset.title == "Genomics dataset"
    assert dataset.description == "Sequencing reads"
    assert dataset.personal_data == Booleanish.YES
    assert dataset.sensitive_data == Booleanish.NO
    assert dataset.dataset_id.identifier == "10.1234/abc"
    assert dataset.dataset_id.type == "doi"
    assert dmp.ethical_issues_exist == Booleanish.YES


def test_dsw_root_reads_contributors_and_projects():
    c_list = r.path(km.CH_ADMIN, km.Q_CONTRIBUTORS)
    c_base = r.path(c_list, "c1")
    p_list = r.path(km.CH_ADMIN, km.Q_PROJECTS)
    p_base = r.path(p_list, "p1")
    f_list = r.path(p_base, km.Q_FUNDING)
    f_base = r.path(f_list, "f1")
    replies = {
        c_list: _reply({"type": "ItemListReply", "value": ["c1"]}),
        r.path(c_base, km.Q_CONTRIB_NAME): _reply(
            {"type": "StringReply", "value": "Grace Hopper"},
        ),
        r.path(c_base, km.Q_CONTRIB_EMAIL): _reply(
            {"type": "StringReply", "value": "grace@example.org"},
        ),
        r.path(c_base, km.Q_CONTRIB_ROLE): _reply(
            {"type": "MultiChoiceReply",
             "value": [km.ROLE_TO_CHOICE["DataManager"]]},
        ),
        p_list: _reply({"type": "ItemListReply", "value": ["p1"]}),
        r.path(p_base, km.Q_PROJ_NAME): _reply(
            {"type": "StringReply", "value": "Big Science"},
        ),
        f_list: _reply({"type": "ItemListReply", "value": ["f1"]}),
        r.path(f_base, km.Q_FUNDER): _reply(
            {"type": "IntegrationReply",
             "value": {"type": "PlainType", "value": "funder:xyz"}},
        ),
        r.path(f_base, km.Q_FUNDING_STATUS): _reply(
            {"type": "AnswerReply",
             "value": km.FUNDING_STATUS_TO_ANSWER["granted"]},
        ),
    }
    dmp = DSWRootProfile().to_dmp(_ctx(replies))

    assert dmp.contributor is not None
    contributor = dmp.contributor[0]
    assert contributor.name == "Grace Hopper"
    assert contributor.mbox == "grace@example.org"
    assert contributor.role == ["DataManager"]

    assert dmp.project is not None
    project = dmp.project[0]
    assert project.title == "Big Science"
    assert project.funding is not None
    # Integration replies unwrap to their plain string value.
    assert project.funding[0].funder_id.identifier == "funder:xyz"
    assert str(project.funding[0].funding_status) == "granted"


def test_dsw_root_write_events_round_trip():
    dmp = DMPData.model_validate(sample_dmp_document()["dmp"])
    profile = DSWRootProfile()
    write = profile.to_write(dmp)

    assert write.settings_payload["name"] == "Test DMP"
    assert write.settings_payload["isTemplate"] is False
    assert write.settings_payload["projectTags"] == []

    # Feed the generated events back through the reader.
    replies = {
        ev["path"]: {"value": ev["value"]} for ev in write.events
    }
    restored = profile.to_dmp(_ctx(replies))
    assert [d.title for d in restored.dataset] == [
        d.title for d in dmp.dataset
    ]
    # The dataset keeps its own identifier (distinct from dmp_id).
    assert restored.dataset[0].dataset_id.identifier == "ds-a"
    assert restored.dataset[0].dataset_id.type == "url"
    assert restored.dataset[0].personal_data == Booleanish.NO
    assert restored.ethical_issues_exist == Booleanish.NO


def test_base_profile_writes_no_events():
    dmp = DMPData.model_validate(sample_dmp_document()["dmp"])
    assert MappingProfile().to_write(dmp).events == []
