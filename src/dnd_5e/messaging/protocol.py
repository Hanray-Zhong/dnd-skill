from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class MessageType(StrEnum):
    CHARACTER_DIALOGUE = "character_dialogue"
    CHARACTER_ACTION = "character_action"
    CHARACTER_INNER = "character_inner"
    OOC = "ooc"
    SYSTEM = "system"


class TablePromptKind(StrEnum):
    ACTION_RESOLUTION_REQUIRED = "action_resolution_required"
    SYSTEM_MESSAGE_VALIDATION_REQUIRED = "system_message_validation_required"


@dataclass(frozen=True)
class ClassifiedMessage:
    message_type: MessageType
    content: str
    explicit: bool


@dataclass(frozen=True)
class MessagePolicy:
    persisted: bool
    audience_scope: Literal["table", "player"]
    prompt_status: Literal["none", "action_required", "validation_required"]
    prompt_kind: TablePromptKind | None = None


class AmbiguousAction(ValueError):
    pass


_POLICIES = {
    MessageType.CHARACTER_DIALOGUE: MessagePolicy(True, "table", "none"),
    MessageType.CHARACTER_ACTION: MessagePolicy(
        True,
        "table",
        "action_required",
        TablePromptKind.ACTION_RESOLUTION_REQUIRED,
    ),
    MessageType.CHARACTER_INNER: MessagePolicy(True, "player", "none"),
    MessageType.OOC: MessagePolicy(False, "table", "none"),
    MessageType.SYSTEM: MessagePolicy(
        False,
        "table",
        "validation_required",
        TablePromptKind.SYSTEM_MESSAGE_VALIDATION_REQUIRED,
    ),
}

PERSISTED_MESSAGE_TYPES = frozenset(
    message_type
    for message_type, policy in _POLICIES.items()
    if policy.persisted
)
CHARACTER_MESSAGE_TYPES = frozenset(
    {
        MessageType.CHARACTER_DIALOGUE,
        MessageType.CHARACTER_ACTION,
        MessageType.CHARACTER_INNER,
    }
)


def classify_message(text: str) -> ClassifiedMessage:
    if text.startswith("//"):
        return ClassifiedMessage(MessageType.OOC, text[2:], True)
    if text.startswith("“") and text.endswith("”") and len(text) > 2:
        return ClassifiedMessage(MessageType.CHARACTER_DIALOGUE, text[1:-1], True)
    if text.startswith("*"):
        if not text.endswith("*") or len(text) <= 2:
            raise AmbiguousAction
        return ClassifiedMessage(MessageType.CHARACTER_ACTION, text[1:-1], True)
    inner_prefix = "（内心："
    if (
        text.startswith(inner_prefix)
        and text.endswith("）")
        and len(text) > len(inner_prefix) + 1
    ):
        return ClassifiedMessage(
            MessageType.CHARACTER_INNER,
            text[len(inner_prefix) : -1],
            True,
        )
    if text.startswith("【") and text.endswith("】") and len(text) > 2:
        return ClassifiedMessage(MessageType.SYSTEM, text[1:-1], True)
    return ClassifiedMessage(MessageType.OOC, text, False)


def message_policy(message_type: MessageType) -> MessagePolicy:
    return _POLICIES[message_type]


def message_audience_id(message_type: MessageType, speaker_id: str) -> str:
    policy = message_policy(message_type)
    return f"player:{speaker_id}" if policy.audience_scope == "player" else "table"


def character_controls(
    configuration: dict[str, object],
) -> dict[str, set[str]]:
    players = configuration.get("players")
    if not isinstance(players, list):
        return {}
    controls: dict[str, set[str]] = {}
    for player in players:
        if not isinstance(player, dict):
            continue
        player_id = player.get("player_id")
        character_ids = player.get("character_ids")
        if not isinstance(player_id, str) or not isinstance(character_ids, list):
            continue
        controls[player_id] = {
            character_id
            for character_id in character_ids
            if isinstance(character_id, str)
        }
    return controls
