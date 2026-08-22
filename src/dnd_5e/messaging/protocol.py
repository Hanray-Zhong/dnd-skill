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


class InteractionMode(StrEnum):
    SHARED_TABLE = "shared_table"


class NarrativeProjection(StrEnum):
    NO_SCENE_FACTS = "no_scene_change"


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


@dataclass(frozen=True)
class MessageScene:
    scene_id: str
    audience_id: str
    interaction_mode: InteractionMode
    narrative_projection: NarrativeProjection
    participant_player_ids: frozenset[str]
    character_controls: dict[str, frozenset[str]]


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
INITIAL_MESSAGE_SCENE_ID = "table"


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


def message_audience_id(
    message_type: MessageType,
    speaker_id: str,
    scene: MessageScene,
) -> str:
    policy = message_policy(message_type)
    return (
        f"player:{speaker_id}"
        if policy.audience_scope == "player"
        else scene.audience_id
    )


def message_scene_entity_id(scene_id: str) -> str:
    return f"scene:{scene_id}"


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


def build_initial_message_scene(
    configuration: dict[str, object],
) -> dict[str, object]:
    controls = character_controls(configuration)
    if not controls:
        raise ValueError("初始消息场景缺少参与玩家")
    return {
        "audience_id": "table",
        "character_controls": {
            player_id: sorted(character_ids)
            for player_id, character_ids in controls.items()
        },
        "interaction_mode": InteractionMode.SHARED_TABLE.value,
        "narrative_projection": NarrativeProjection.NO_SCENE_FACTS.value,
        "participant_player_ids": list(controls),
        "scene_id": INITIAL_MESSAGE_SCENE_ID,
    }


def parse_message_scene(value: object) -> MessageScene:
    if not isinstance(value, dict) or set(value) != {
        "audience_id",
        "character_controls",
        "interaction_mode",
        "narrative_projection",
        "participant_player_ids",
        "scene_id",
    }:
        raise ValueError("消息场景结构无效")
    scene_id = value.get("scene_id")
    audience_id = value.get("audience_id")
    participant_value = value.get("participant_player_ids")
    controls_value = value.get("character_controls")
    if (
        not isinstance(scene_id, str)
        or not scene_id.strip()
        or not isinstance(audience_id, str)
        or not audience_id.strip()
        or value.get("interaction_mode") != InteractionMode.SHARED_TABLE.value
        or value.get("narrative_projection")
        != NarrativeProjection.NO_SCENE_FACTS.value
        or not isinstance(participant_value, list)
        or not participant_value
        or not all(
            isinstance(player_id, str) and bool(player_id.strip())
            for player_id in participant_value
        )
        or len(set(participant_value)) != len(participant_value)
        or not isinstance(controls_value, dict)
        or set(controls_value) != set(participant_value)
    ):
        raise ValueError("消息场景内容无效")
    controls: dict[str, frozenset[str]] = {}
    for player_id, character_ids in controls_value.items():
        if (
            not isinstance(player_id, str)
            or not isinstance(character_ids, list)
            or not all(
                isinstance(character_id, str) and bool(character_id.strip())
                for character_id in character_ids
            )
            or len(set(character_ids)) != len(character_ids)
        ):
            raise ValueError("消息场景角色控制无效")
        controls[player_id] = frozenset(character_ids)
    return MessageScene(
        scene_id=scene_id,
        audience_id=audience_id,
        interaction_mode=InteractionMode.SHARED_TABLE,
        narrative_projection=NarrativeProjection.NO_SCENE_FACTS,
        participant_player_ids=frozenset(participant_value),
        character_controls=controls,
    )
