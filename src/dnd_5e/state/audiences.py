from __future__ import annotations

import json
import sqlite3

from dnd_5e.state.types import AudienceMap, InvalidStateRequest


_AUDIENCE_TYPES = {"dm", "player", "table"}


def validate_audiences(
    value: object,
    *,
    required_audience_id: str | None = None,
) -> AudienceMap:
    if not isinstance(value, dict):
        raise InvalidStateRequest("输出受众配置必须是 object")
    audiences: AudienceMap = {}
    for audience_id, definition in value.items():
        if (
            not isinstance(audience_id, str)
            or not audience_id.strip()
            or not isinstance(definition, dict)
            or set(definition) != {"audience_type", "members"}
        ):
            raise InvalidStateRequest("输出受众定义无效")
        audience_type = definition.get("audience_type")
        members = definition.get("members")
        if (
            not isinstance(audience_type, str)
            or audience_type not in _AUDIENCE_TYPES
            or not isinstance(members, list)
            or not all(isinstance(member, str) and member.strip() for member in members)
            or len(set(members)) != len(members)
        ):
            raise InvalidStateRequest("输出受众定义无效")
        audiences[audience_id] = {
            "audience_type": audience_type,
            "members": members,
        }
    if audiences.get("dm") != {"audience_type": "dm", "members": []}:
        raise InvalidStateRequest("输出受众配置缺少合法 DM 受众")
    player_members: list[str] = []
    for audience_id, definition in audiences.items():
        audience_type = definition["audience_type"]
        members = definition["members"]
        if audience_type == "dm" and audience_id != "dm":
            raise InvalidStateRequest("DM 受众标识无效")
        if audience_type == "player":
            if len(members) != 1 or audience_id != f"player:{members[0]}":
                raise InvalidStateRequest("玩家受众定义无效")
            player_members.extend(members)
        if audience_type == "table" and audience_id != "table":
            raise InvalidStateRequest("桌级受众标识无效")
    table = audiences.get("table")
    if player_members or table is not None:
        if (
            table is None
            or table["audience_type"] != "table"
            or set(table["members"]) != set(player_members)
        ):
            raise InvalidStateRequest("桌级与玩家受众成员不一致")
    if required_audience_id is not None and required_audience_id not in audiences:
        raise InvalidStateRequest("事件受众不在输出受众配置中")
    return audiences


def read_audiences(
    connection: sqlite3.Connection,
) -> AudienceMap:
    rows = connection.execute(
        "SELECT audience_id, audience_type, definition_json FROM audiences"
    ).fetchall()
    raw_audiences: dict[str, object] = {}
    for audience_id, audience_type, definition_json in rows:
        definition = json.loads(definition_json)
        members = definition.get("members") if isinstance(definition, dict) else None
        if definition == {} and audience_id == "dm" and audience_type == "dm":
            members = []
        if not isinstance(audience_id, str):
            raise sqlite3.DatabaseError("输出受众配置损坏")
        raw_audiences[audience_id] = {
            "audience_type": audience_type,
            "members": members,
        }
    try:
        return validate_audiences(raw_audiences)
    except InvalidStateRequest as error:
        raise sqlite3.DatabaseError("输出受众配置损坏") from error
