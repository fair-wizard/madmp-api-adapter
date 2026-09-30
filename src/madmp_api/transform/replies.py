"""Helpers for reading and writing Wizard questionnaire replies.

Wizard stores replies in a flat map keyed by a dot-joined UUID *path*:

* ``chapter.question`` — a plain question
* ``chapter.list.item.question`` — a question inside a list item

Reply values are tagged unions, e.g. ``{"type": "StringReply", "value": …}``.
"""

import uuid
from typing import Any

Replies = dict[str, Any]


def path(*parts: str) -> str:
    return '.'.join(parts)


def raw_value(replies: Replies, key: str) -> object:
    """Return the untagged ``value`` of a reply, or None when absent."""
    reply = replies.get(key)
    if not isinstance(reply, dict):
        return None
    value = reply.get('value')
    if not isinstance(value, dict):
        return None
    return value.get('value')


def string_value(replies: Replies, key: str) -> str | None:
    value = raw_value(replies, key)
    if isinstance(value, str):
        return value.strip() or None
    # Integration replies nest their own tagged value.
    if isinstance(value, dict):
        inner = value.get('value')
        if isinstance(inner, str):
            return inner.strip() or None
    return None


def answer_value(replies: Replies, key: str) -> str | None:
    value = raw_value(replies, key)
    return value if isinstance(value, str) else None


def list_items(replies: Replies, key: str) -> list[str]:
    value = raw_value(replies, key)
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def choice_values(replies: Replies, key: str) -> list[str]:
    return list_items(replies, key)


def new_uuid() -> str:
    return str(uuid.uuid4())


def set_reply(reply_path: str, value: dict[str, Any]) -> dict[str, Any]:
    return {
        'type': 'SetReplyEvent',
        'uuid': new_uuid(),
        'path': reply_path,
        'value': value,
    }


def string_reply(value: str) -> dict[str, Any]:
    return {'type': 'StringReply', 'value': value}


def answer_reply(value: str) -> dict[str, Any]:
    return {'type': 'AnswerReply', 'value': value}


def item_list_reply(values: list[str]) -> dict[str, Any]:
    return {'type': 'ItemListReply', 'value': values}


def multi_choice_reply(values: list[str]) -> dict[str, Any]:
    return {'type': 'MultiChoiceReply', 'value': values}


def integration_reply(value: str) -> dict[str, Any]:
    return {
        'type': 'IntegrationReply',
        'value': {'type': 'PlainType', 'value': value},
    }
