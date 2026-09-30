"""Mapping profiles between Wizard projects and RDA maDMP documents.

:class:`MappingProfile` is knowledge-model agnostic: it produces a *valid*
maDMP (all RDA-required fields present) from data available on every Wizard
project — settings plus the authenticated user — and synthesises the RDA
identifiers.

:class:`DSWRootProfile` extends it with the real question mapping of the
Common DSW Knowledge Model (``dsw:root``), reading questionnaire replies
into datasets/contributors/projects/costs and writing them back as reply
events.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from madmp_api.madmp.models import (
    Booleanish,
    Contact,
    Contributor,
    Cost,
    Dataset,
    DMPData,
    Funding,
    Identifier,
    Project,
)
from madmp_api.transform import dsw_root as km
from madmp_api.transform import replies as r


@dataclass
class ProjectContext:
    uuid: str
    settings: dict[str, Any]
    questionnaire: dict[str, Any]
    user: dict[str, Any]
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Tenant-derived synthesis defaults (see ``madmp_api.tenancy``).
    dmp_id_base_url: str = 'http://localhost:8000/dmps'
    default_language: str = 'eng'


@dataclass
class WizardWrite:
    settings_payload: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)


def _full_name(user: dict[str, Any]) -> str:
    if user.get('name'):
        return str(user['name'])
    parts = [user.get('firstName'), user.get('lastName')]
    joined = ' '.join(str(part) for part in parts if part)
    return joined or 'Unknown'


def _booleanish(value: str | None, yes: str, no: str) -> Booleanish:
    if value == yes:
        return Booleanish.YES
    if value == no:
        return Booleanish.NO
    return Booleanish.UNKNOWN


def _date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        return None


class MappingProfile:
    def to_dmp(self, ctx: ProjectContext) -> DMPData:
        name = ctx.settings.get('name') or 'Untitled DMP'
        created = ctx.created_at or ctx.updated_at or datetime.now(UTC)
        modified = ctx.updated_at or created
        dmp_identifier = f'{ctx.dmp_id_base_url}/{ctx.uuid}'
        datasets = self.datasets(ctx, dmp_identifier) or [
            self._default_dataset(name, dmp_identifier),
        ]
        return DMPData(
            title=name,
            description=ctx.settings.get('description'),
            created=created,
            modified=modified,
            language=ctx.settings.get('language') or ctx.default_language,
            dmp_id=Identifier(identifier=dmp_identifier, type='url'),
            contact=self._contact(ctx),
            dataset=datasets,
            contributor=self.contributors(ctx) or None,
            project=self.projects(ctx) or None,
            cost=self.costs(ctx) or None,
            ethical_issues_exist=self.ethical_issues_exist(ctx),
        )

    def _contact(self, ctx: ProjectContext) -> Contact:
        user = ctx.user or {}
        mbox = str(user.get('email') or 'unknown@example.org')
        identifier = str(user.get('uuid') or mbox)
        return Contact(
            name=_full_name(user),
            mbox=mbox,
            contact_id=Identifier(identifier=identifier, type='other'),
        )

    def _default_dataset(self, title: str, dmp_id: str) -> Dataset:
        return Dataset(
            title=title,
            dataset_id=Identifier(
                identifier=f'{dmp_id}/datasets/1',
                type='url',
            ),
            personal_data=Booleanish.UNKNOWN,
            sensitive_data=Booleanish.UNKNOWN,
        )

    # --- KM-specific extension hooks (no-ops in the base profile) -------

    def datasets(self, ctx: ProjectContext, dmp_id: str) -> list[Dataset]:
        _ = (ctx, dmp_id)
        return []

    def contributors(self, ctx: ProjectContext) -> list[Contributor]:
        _ = ctx
        return []

    def projects(self, ctx: ProjectContext) -> list[Project]:
        _ = ctx
        return []

    def costs(self, ctx: ProjectContext) -> list[Cost]:
        _ = ctx
        return []

    def ethical_issues_exist(self, ctx: ProjectContext) -> Booleanish:
        _ = ctx
        return Booleanish.UNKNOWN

    # --- maDMP -> Wizard (writes) ------------------------------------------

    def to_write(self, dmp: DMPData) -> WizardWrite:
        return WizardWrite(
            settings_payload={
                'name': dmp.title,
                'description': dmp.description,
                'isTemplate': False,
                'projectTags': [],
            },
            events=self.to_events(dmp),
        )

    def to_events(self, dmp: DMPData) -> list[dict[str, Any]]:
        _ = dmp
        return []


class DSWRootProfile(MappingProfile):
    """Mapping for the Common DSW Knowledge Model (``dsw:root``)."""

    def _replies(self, ctx: ProjectContext) -> r.Replies:
        replies = ctx.questionnaire.get('replies')
        return replies if isinstance(replies, dict) else {}

    def datasets(self, ctx: ProjectContext, dmp_id: str) -> list[Dataset]:
        replies = self._replies(ctx)
        list_path = r.path(km.CH_PRESERVE, km.Q_DATASETS)
        datasets: list[Dataset] = []
        for index, item in enumerate(r.list_items(replies, list_path), 1):
            base = r.path(list_path, item)
            title = (
                r.string_value(replies, r.path(base, km.Q_DS_TITLE))
                or f'Dataset {index}'
            )
            datasets.append(
                Dataset(
                    title=title,
                    description=r.string_value(
                        replies,
                        r.path(base, km.Q_DS_DESCRIPTION),
                    ),
                    dataset_id=self._dataset_id(
                        replies,
                        base,
                        f'{dmp_id}/datasets/{item}',
                    ),
                    personal_data=_booleanish(
                        r.answer_value(
                            replies,
                            r.path(base, km.Q_DS_PERSONAL),
                        ),
                        km.A_PERSONAL_YES,
                        km.A_PERSONAL_NO,
                    ),
                    sensitive_data=_booleanish(
                        r.answer_value(
                            replies,
                            r.path(base, km.Q_DS_SENSITIVE),
                        ),
                        km.A_SENSITIVE_YES,
                        km.A_SENSITIVE_NO,
                    ),
                ),
            )
        return datasets

    def _dataset_id(
        self,
        replies: r.Replies,
        base: str,
        fallback: str,
    ) -> Identifier:
        id_list = r.path(base, km.Q_DS_IDENTIFIERS)
        for item in r.list_items(replies, id_list):
            id_base = r.path(id_list, item)
            value = r.string_value(
                replies,
                r.path(id_base, km.Q_DS_ID_VALUE),
            )
            if not value:
                continue
            answer = r.answer_value(
                replies,
                r.path(id_base, km.Q_DS_ID_TYPE),
            )
            return Identifier(
                identifier=value,
                type=km.ID_TYPE_ANSWERS.get(answer or '', 'other'),
            )
        return Identifier(identifier=fallback, type='url')

    def contributors(self, ctx: ProjectContext) -> list[Contributor]:
        replies = self._replies(ctx)
        list_path = r.path(km.CH_ADMIN, km.Q_CONTRIBUTORS)
        contributors: list[Contributor] = []
        for item in r.list_items(replies, list_path):
            base = r.path(list_path, item)
            name = r.string_value(replies, r.path(base, km.Q_CONTRIB_NAME))
            if not name:
                continue
            orcid = r.string_value(
                replies,
                r.path(base, km.Q_CONTRIB_ORCID),
            )
            roles = [
                km.ROLE_CHOICES[choice]
                for choice in r.choice_values(
                    replies,
                    r.path(base, km.Q_CONTRIB_ROLE),
                )
                if choice in km.ROLE_CHOICES
            ]
            contributors.append(
                Contributor(
                    name=name,
                    mbox=r.string_value(
                        replies,
                        r.path(base, km.Q_CONTRIB_EMAIL),
                    ),
                    role=roles or ['Other'],
                    contributor_id=Identifier(
                        identifier=orcid or name,
                        type='orcid' if orcid else 'other',
                    ),
                ),
            )
        return contributors

    def projects(self, ctx: ProjectContext) -> list[Project]:
        replies = self._replies(ctx)
        list_path = r.path(km.CH_ADMIN, km.Q_PROJECTS)
        projects: list[Project] = []
        for item in r.list_items(replies, list_path):
            base = r.path(list_path, item)
            title = r.string_value(replies, r.path(base, km.Q_PROJ_NAME))
            if not title:
                continue
            projects.append(
                Project(
                    title=title,
                    description=r.string_value(
                        replies,
                        r.path(base, km.Q_PROJ_ABSTRACT),
                    ),
                    start=_date(
                        r.string_value(
                            replies,
                            r.path(base, km.Q_PROJ_START),
                        ),
                    ),
                    end=_date(
                        r.string_value(replies, r.path(base, km.Q_PROJ_END)),
                    ),
                    funding=self._fundings(replies, base) or None,
                ),
            )
        return projects

    def _fundings(
        self,
        replies: r.Replies,
        project_base: str,
    ) -> list[Funding]:
        list_path = r.path(project_base, km.Q_FUNDING)
        fundings: list[Funding] = []
        for item in r.list_items(replies, list_path):
            base = r.path(list_path, item)
            funder = r.string_value(replies, r.path(base, km.Q_FUNDER))
            if not funder:
                continue
            grant = r.string_value(replies, r.path(base, km.Q_GRANT))
            status = km.FUNDING_STATUS_ANSWERS.get(
                r.answer_value(replies, r.path(base, km.Q_FUNDING_STATUS))
                or '',
            )
            fundings.append(
                Funding(
                    funder_id=Identifier(identifier=funder, type='url'),
                    grant_id=(
                        Identifier(identifier=grant, type='url')
                        if grant
                        else None
                    ),
                    funding_status=status,
                ),
            )
        return fundings

    def costs(self, ctx: ProjectContext) -> list[Cost]:
        replies = self._replies(ctx)
        project_list = r.path(km.CH_ADMIN, km.Q_PROJECTS)
        costs: list[Cost] = []
        for project_item in r.list_items(replies, project_list):
            list_path = r.path(project_list, project_item, km.Q_COSTS)
            for item in r.list_items(replies, list_path):
                base = r.path(list_path, item)
                title = r.string_value(
                    replies,
                    r.path(base, km.Q_COST_TITLE),
                )
                if not title:
                    continue
                costs.append(
                    Cost(
                        title=title,
                        description=r.string_value(
                            replies,
                            r.path(base, km.Q_COST_DESCRIPTION),
                        ),
                        value=_number(
                            r.string_value(
                                replies,
                                r.path(base, km.Q_COST_AMOUNT),
                            ),
                        ),
                        currency_code=r.string_value(
                            replies,
                            r.path(base, km.Q_COST_CURRENCY),
                        ),
                    ),
                )
        return costs

    def ethical_issues_exist(self, ctx: ProjectContext) -> Booleanish:
        return _booleanish(
            r.answer_value(
                self._replies(ctx),
                r.path(km.CH_COLLECT, km.Q_ETHICAL),
            ),
            km.A_ETHICAL_YES,
            km.A_ETHICAL_NO,
        )

    # --- maDMP -> Wizard reply events --------------------------------------

    def to_events(self, dmp: DMPData) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        events.extend(self._dataset_events(dmp))
        events.extend(self._contributor_events(dmp))
        events.extend(self._project_events(dmp))
        events.append(
            r.set_reply(
                r.path(km.CH_COLLECT, km.Q_ETHICAL),
                r.answer_reply(
                    km.A_ETHICAL_YES
                    if dmp.ethical_issues_exist == Booleanish.YES
                    else km.A_ETHICAL_NO,
                ),
            ),
        )
        return events

    def _dataset_events(self, dmp: DMPData) -> list[dict[str, Any]]:
        list_path = r.path(km.CH_PRESERVE, km.Q_DATASETS)
        events: list[dict[str, Any]] = []
        items: list[str] = []
        for dataset in dmp.dataset:
            item = r.new_uuid()
            items.append(item)
            base = r.path(list_path, item)
            events.append(
                r.set_reply(
                    r.path(base, km.Q_DS_TITLE),
                    r.string_reply(dataset.title),
                ),
            )
            if dataset.description:
                events.append(
                    r.set_reply(
                        r.path(base, km.Q_DS_DESCRIPTION),
                        r.string_reply(dataset.description),
                    ),
                )
            events.extend(self._dataset_id_events(dataset, base))
            events.extend(
                [
                    r.set_reply(
                        r.path(base, km.Q_DS_PERSONAL),
                        r.answer_reply(
                            km.A_PERSONAL_YES
                            if dataset.personal_data == Booleanish.YES
                            else km.A_PERSONAL_NO,
                        ),
                    ),
                    r.set_reply(
                        r.path(base, km.Q_DS_SENSITIVE),
                        r.answer_reply(
                            km.A_SENSITIVE_YES
                            if dataset.sensitive_data == Booleanish.YES
                            else km.A_SENSITIVE_NO,
                        ),
                    ),
                ],
            )
        events.insert(0, r.set_reply(list_path, r.item_list_reply(items)))
        return events

    def _dataset_id_events(
        self,
        dataset: Dataset,
        base: str,
    ) -> list[dict[str, Any]]:
        id_list = r.path(base, km.Q_DS_IDENTIFIERS)
        item = r.new_uuid()
        id_base = r.path(id_list, item)
        answer = km.ID_TYPE_TO_ANSWER.get(
            dataset.dataset_id.type,
            km.ID_TYPE_TO_ANSWER['other'],
        )
        return [
            r.set_reply(id_list, r.item_list_reply([item])),
            r.set_reply(
                r.path(id_base, km.Q_DS_ID_VALUE),
                r.string_reply(dataset.dataset_id.identifier),
            ),
            r.set_reply(
                r.path(id_base, km.Q_DS_ID_TYPE),
                r.answer_reply(answer),
            ),
        ]

    def _contributor_events(self, dmp: DMPData) -> list[dict[str, Any]]:
        list_path = r.path(km.CH_ADMIN, km.Q_CONTRIBUTORS)
        events: list[dict[str, Any]] = []
        items: list[str] = []
        for contributor in dmp.contributor or []:
            item = r.new_uuid()
            items.append(item)
            base = r.path(list_path, item)
            events.append(
                r.set_reply(
                    r.path(base, km.Q_CONTRIB_NAME),
                    r.string_reply(contributor.name),
                ),
            )
            if contributor.mbox:
                events.append(
                    r.set_reply(
                        r.path(base, km.Q_CONTRIB_EMAIL),
                        r.string_reply(contributor.mbox),
                    ),
                )
            choices = [
                km.ROLE_TO_CHOICE[role]
                for role in contributor.role
                if role in km.ROLE_TO_CHOICE
            ]
            if choices:
                events.append(
                    r.set_reply(
                        r.path(base, km.Q_CONTRIB_ROLE),
                        r.multi_choice_reply(choices),
                    ),
                )
        if not items:
            return []
        events.insert(0, r.set_reply(list_path, r.item_list_reply(items)))
        return events

    def _project_events(self, dmp: DMPData) -> list[dict[str, Any]]:
        list_path = r.path(km.CH_ADMIN, km.Q_PROJECTS)
        events: list[dict[str, Any]] = []
        items: list[str] = []
        for project in dmp.project or []:
            item = r.new_uuid()
            items.append(item)
            base = r.path(list_path, item)
            events.append(
                r.set_reply(
                    r.path(base, km.Q_PROJ_NAME),
                    r.string_reply(project.title),
                ),
            )
            if project.description:
                events.append(
                    r.set_reply(
                        r.path(base, km.Q_PROJ_ABSTRACT),
                        r.string_reply(project.description),
                    ),
                )
            events.extend(self._funding_events(project, base))
        if not items:
            return []
        events.insert(0, r.set_reply(list_path, r.item_list_reply(items)))
        return events

    def _funding_events(
        self,
        project: Project,
        project_base: str,
    ) -> list[dict[str, Any]]:
        list_path = r.path(project_base, km.Q_FUNDING)
        events: list[dict[str, Any]] = []
        items: list[str] = []
        for funding in project.funding or []:
            item = r.new_uuid()
            items.append(item)
            base = r.path(list_path, item)
            events.append(
                r.set_reply(
                    r.path(base, km.Q_FUNDER),
                    r.integration_reply(funding.funder_id.identifier),
                ),
            )
            if funding.grant_id:
                events.append(
                    r.set_reply(
                        r.path(base, km.Q_GRANT),
                        r.string_reply(funding.grant_id.identifier),
                    ),
                )
            answer = km.FUNDING_STATUS_TO_ANSWER.get(
                str(funding.funding_status or ''),
            )
            if answer:
                events.append(
                    r.set_reply(
                        r.path(base, km.Q_FUNDING_STATUS),
                        r.answer_reply(answer),
                    ),
                )
        if not items:
            return []
        events.insert(0, r.set_reply(list_path, r.item_list_reply(items)))
        return events


def _number(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


_BASE_PROFILE = MappingProfile()
_DSW_ROOT_PROFILE = DSWRootProfile()


def get_profile(km_id: str | None) -> MappingProfile:
    """Select a profile from a ``org:kmId:version`` package identifier."""
    if km_id and km_id.startswith('dsw:root:'):
        return _DSW_ROOT_PROFILE
    return _BASE_PROFILE
