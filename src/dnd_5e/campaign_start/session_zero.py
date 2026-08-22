from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import uuid

from dnd_5e.errors import FacadeError
from dnd_5e.state.session_zero import commit_session_zero
from dnd_5e.state.types import (
    AudienceMap,
    IdempotencyConflict,
    InvalidStateRequest,
    RevisionConflict,
    SessionZeroCompletion,
    SessionZeroRequest,
)
from dnd_5e.workspace import (
    _created_at,
    _invalid_state_store,
    _load_existing_campaign,
)


_PVP_STRICTNESS = {"allow": 0, "ask": 1, "forbid": 2}
_ADVANCEMENT_METHODS = {"xp", "milestone"}
_ABSENCE_MODES = {"narrative_exit", "delegate", "agent_custody"}
_PLAYER_ROLL_POLICIES = {"player_rolls", "script_rolls"}
_PRIVATE_ROLL_POLICIES = {"dice_engine", "private_pool"}


@dataclass(frozen=True)
class NormalizedSessionZero:
    configuration: dict[str, object]
    audiences: AudienceMap


def _normalize_configuration(
    configuration: dict[str, object],
    current_config: dict[str, object],
) -> NormalizedSessionZero:
    required_fields = ("players", "safety", "pvp_categories")
    missing_fields = [
        field for field in required_fields if field not in configuration
    ]
    if missing_fields:
        raise FacadeError(
            "invalid_session_zero",
            "Session Zero 配置缺少开团所需的必填决策。",
            {"missing_fields": missing_fields},
        )
    players_value = configuration.get("players")
    categories_value = configuration.get("pvp_categories")
    if not isinstance(players_value, list) or not isinstance(categories_value, list):
        raise FacadeError(
            "invalid_session_zero",
            "Session Zero 配置缺少玩家名单或 PvP 行为类别。",
        )

    invalid_fields: list[str] = []
    defaulted_fields: list[str] = []
    if not players_value:
        invalid_fields.append("players")

    def resolve_root_default(field: str, fallback: object) -> object:
        if field in configuration:
            return configuration[field]
        defaulted_fields.append(field)
        return current_config.get(field, fallback)

    advancement = resolve_root_default("advancement", "xp")
    difficulty = resolve_root_default("difficulty", "standard")
    private_roll_policy = resolve_root_default(
        "private_roll_policy",
        "dice_engine",
    )
    if advancement not in _ADVANCEMENT_METHODS:
        invalid_fields.append("advancement")
    if not isinstance(difficulty, str) or not difficulty.strip():
        invalid_fields.append("difficulty")
    if private_roll_policy not in _PRIVATE_ROLL_POLICIES:
        invalid_fields.append("private_roll_policy")
    if "roll_policy" in configuration:
        invalid_fields.append("roll_policy")
    categories_are_valid = (
        bool(categories_value)
        and all(
            isinstance(category, str) and bool(category.strip())
            for category in categories_value
        )
        and len(set(categories_value)) == len(categories_value)
    )
    if not categories_are_valid:
        invalid_fields.append("pvp_categories")
    safety_value = configuration.get("safety")
    boundaries = (
        safety_value.get("boundaries")
        if isinstance(safety_value, dict)
        else None
    )
    if not isinstance(boundaries, list) or not all(
        isinstance(boundary, str) and bool(boundary.strip())
        for boundary in boundaries
    ):
        invalid_fields.append("safety.boundaries")

    players: list[dict[str, object]] = []
    player_ids: list[str] = []
    character_controls: dict[str, list[str]] = {}
    delegate_targets: list[tuple[str, str, object]] = []
    for player_index, player_value in enumerate(players_value):
        if not isinstance(player_value, dict):
            raise FacadeError(
                "invalid_session_zero",
                "Session Zero 玩家配置无效。",
            )
        player_id = player_value.get("player_id")
        if not isinstance(player_id, str):
            raise FacadeError(
                "invalid_session_zero",
                "Session Zero 玩家标识无效。",
            )
        player_label = player_id if player_id.strip() else str(player_index)
        if not player_id.strip():
            invalid_fields.append(f"players[{player_index}].player_id")
        display_name = player_value.get("display_name")
        character_ids = player_value.get("character_ids")
        player_preferences = player_value.get("preferences")
        if not isinstance(display_name, str) or not display_name.strip():
            invalid_fields.append(f"players[{player_label}].display_name")
        if not isinstance(character_ids, list) or not all(
            isinstance(character_id, str) and bool(character_id.strip())
            for character_id in character_ids
        ):
            invalid_fields.append(f"players[{player_label}].character_ids")
        valid_character_ids = (
            [value for value in character_ids if isinstance(value, str)]
            if isinstance(character_ids, list)
            else []
        )
        if not isinstance(player_preferences, dict):
            invalid_fields.append(f"players[{player_label}].preferences")
        preferences_value = player_value.get("pvp_preferences")
        if preferences_value is None:
            preferences: dict[str, object] = {}
        elif isinstance(preferences_value, dict):
            preferences = preferences_value
        else:
            preferences = {}
            invalid_fields.append(f"players[{player_label}].pvp_preferences")
        if "roll_policy" in player_value:
            roll_policy = player_value["roll_policy"]
        else:
            roll_policy = "player_rolls"
            defaulted_fields.append(f"players[{player_label}].roll_policy")
        if roll_policy not in _PLAYER_ROLL_POLICIES:
            invalid_fields.append(f"players[{player_label}].roll_policy")

        if "absence_policy" in player_value:
            invalid_fields.append(f"players[{player_label}].absence_policy")
        absence_policies_value = player_value.get("absence_policies")
        if absence_policies_value is None:
            absence_policies: dict[str, object] = {}
        elif isinstance(absence_policies_value, dict):
            absence_policies = absence_policies_value
        else:
            absence_policies = {}
            invalid_fields.append(f"players[{player_label}].absence_policies")
        for character_id in absence_policies:
            if character_id not in valid_character_ids:
                invalid_fields.append(
                    f"players[{player_label}].absence_policies.{character_id}"
                )
        normalized_absence_policies: dict[str, object] = {}
        for character_id in valid_character_ids:
            absence_policy = absence_policies.get(character_id)
            field = f"players[{player_label}].absence_policies.{character_id}"
            if absence_policy is None:
                absence_policy = {"mode": "narrative_exit"}
                defaulted_fields.append(field)
            if not isinstance(absence_policy, dict):
                invalid_fields.append(field)
                continue
            absence_mode = absence_policy.get("mode")
            if absence_mode not in _ABSENCE_MODES:
                invalid_fields.append(f"{field}.mode")
            elif absence_mode == "delegate":
                delegate_targets.append(
                    (
                        player_label,
                        character_id,
                        absence_policy.get("delegate_player_id"),
                    )
                )
            normalized_absence_policies[character_id] = absence_policy

        normalized_pvp_preferences: dict[str, object] = {}
        for category in categories_value:
            if not isinstance(category, str):
                continue
            field = f"players[{player_label}].pvp_preferences.{category}"
            if category not in preferences:
                decision: object = "forbid"
                defaulted_fields.append(field)
            else:
                decision = preferences[category]
            if not isinstance(decision, str) or decision not in _PVP_STRICTNESS:
                invalid_fields.append(field)
            normalized_pvp_preferences[category] = decision

        normalized_player = {
            **player_value,
            "absence_policies": normalized_absence_policies,
            "pvp_preferences": normalized_pvp_preferences,
            "roll_policy": roll_policy,
        }
        normalized_player.pop("absence_policy", None)
        players.append(normalized_player)
        player_ids.append(player_id)
        if isinstance(character_ids, list):
            for character_id in character_ids:
                if isinstance(character_id, str):
                    character_controls.setdefault(character_id, []).append(player_id)

    duplicate_player_ids = sorted(
        player_id
        for player_id, count in Counter(player_ids).items()
        if count > 1
    )
    if duplicate_player_ids:
        raise FacadeError(
            "session_zero_conflict",
            "Session Zero 配置包含重复的玩家稳定标识。",
            {"duplicate_player_ids": duplicate_player_ids},
        )

    for player_id, character_id, delegate_target in delegate_targets:
        if (
            not isinstance(delegate_target, str)
            or delegate_target not in player_ids
            or delegate_target == player_id
        ):
            invalid_fields.append(
                "players["
                f"{player_id}].absence_policies.{character_id}.delegate_player_id"
            )
    if invalid_fields:
        raise FacadeError(
            "invalid_session_zero",
            "Session Zero 配置包含不支持或无效的决策。",
            {"invalid_fields": sorted(invalid_fields)},
        )

    conflicting_controls = {
        character_id: controllers
        for character_id, controllers in character_controls.items()
        if len(controllers) > 1
    }
    if conflicting_controls:
        raise FacadeError(
            "session_zero_conflict",
            "Session Zero 配置存在互相冲突的角色控制关系。",
            {"character_controls": conflicting_controls},
        )

    safety = configuration.get("safety")
    confirmed_by = safety.get("confirmed_by") if isinstance(safety, dict) else None
    safety_confirmations = (
        {value for value in confirmed_by if isinstance(value, str)}
        if isinstance(confirmed_by, list)
        else set()
    )
    missing_player_confirmations = [
        player_id
        for player_id, player in zip(player_ids, players, strict=True)
        if player.get("confirmed") is not True
    ]
    missing_safety_confirmations = [
        player_id
        for player_id in player_ids
        if player_id not in safety_confirmations
    ]
    categories = [
        category for category in categories_value if isinstance(category, str)
    ]
    pvp_policy: dict[str, str] = {}
    for category in categories:
        strictest = "allow"
        for player in players:
            normalized_preferences_value = player.get("pvp_preferences")
            decision = (
                normalized_preferences_value.get(category)
                if isinstance(normalized_preferences_value, dict)
                else None
            )
            if not isinstance(decision, str) or decision not in _PVP_STRICTNESS:
                decision = "forbid"
            if _PVP_STRICTNESS[decision] > _PVP_STRICTNESS[strictest]:
                strictest = decision
        pvp_policy[category] = strictest

    merged_configuration = {
        **current_config,
        **configuration,
        "advancement": advancement,
        "difficulty": difficulty,
        "players": players,
        "private_roll_policy": private_roll_policy,
        "pvp_policy": pvp_policy,
    }
    merged_configuration.pop("roll_policy", None)
    normalized = json.loads(
        json.dumps(
            merged_configuration,
            ensure_ascii=False,
            allow_nan=False,
        )
    )
    if not isinstance(normalized, dict):
        raise AssertionError("规范化后的 Session Zero 配置必须是 object")

    audiences: AudienceMap = {
        "dm": {"audience_type": "dm", "members": []},
        "table": {"audience_type": "table", "members": player_ids},
    }
    for player_id in player_ids:
        audiences[f"player:{player_id}"] = {
            "audience_type": "player",
            "members": [player_id],
        }
    normalized_defaulted_fields = tuple(sorted(set(defaulted_fields)))
    if normalized_defaulted_fields:
        raise FacadeError(
            "session_zero_confirmation_required",
            "Session Zero 默认值必须先显式展示并由玩家确认。",
            {
                "defaulted_fields": list(normalized_defaulted_fields),
                "resolved_configuration": normalized,
            },
        )
    if missing_player_confirmations or missing_safety_confirmations:
        raise FacadeError(
            "session_zero_incomplete",
            "Session Zero 尚未获得全部必要确认，不能开团。",
            {
                "missing_player_confirmations": missing_player_confirmations,
                "missing_safety_confirmations": missing_safety_confirmations,
            },
        )
    return NormalizedSessionZero(
        configuration=normalized,
        audiences=audiences,
    )


def complete_session_zero(
    workspace: Path,
    *,
    expected_revision: int,
    idempotency_key: str,
    configuration: dict[str, object],
) -> SessionZeroCompletion:
    if expected_revision < 1 or not idempotency_key.strip():
        raise FacadeError(
            "invalid_state_request",
            "状态变更请求必须包含有效修订号和幂等键。",
        )
    _, database_path, current = _load_existing_campaign(workspace)
    normalized = _normalize_configuration(
        configuration,
        current.initial_config,
    )
    request = SessionZeroRequest(
        expected_revision=expected_revision,
        idempotency_key=idempotency_key,
        configuration=normalized.configuration,
        audiences=normalized.audiences,
        source="dnd-5e-campaign-start",
        audience_id="dm",
    )
    try:
        return commit_session_zero(
            database_path,
            request=request,
            event_id=str(uuid.uuid4()),
            committed_at=_created_at(),
        )
    except RevisionConflict as error:
        raise FacadeError(
            "revision_conflict",
            "状态变更请求基于过期修订，必须先重新打开战役并重新对账。",
            {
                "expected_revision": expected_revision,
                "current_revision": error.current.revision,
                "current_config": error.current.initial_config,
            },
        ) from error
    except IdempotencyConflict as error:
        raise FacadeError(
            "idempotency_conflict",
            "该幂等键已用于不同的状态变更请求。",
        ) from error
    except InvalidStateRequest as error:
        raise FacadeError(
            "invalid_state_request",
            "状态变更请求包含无效的 Session Zero 受众配置。",
        ) from error
    except (OSError, sqlite3.Error) as error:
        raise FacadeError(
            "state_commit_failed",
            "状态事务写入失败，未提交任何部分状态。",
        ) from error
    except (TypeError, ValueError) as error:
        raise _invalid_state_store() from error
