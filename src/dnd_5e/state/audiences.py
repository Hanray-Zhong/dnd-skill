from __future__ import annotations

import json
import sqlite3


def read_audiences(
    connection: sqlite3.Connection,
) -> dict[str, dict[str, object]]:
    rows = connection.execute(
        "SELECT audience_id, audience_type, definition_json FROM audiences"
    ).fetchall()
    audiences: dict[str, dict[str, object]] = {}
    for audience_id, audience_type, definition_json in rows:
        definition = json.loads(definition_json)
        members = definition.get("members") if isinstance(definition, dict) else None
        if definition == {} and audience_id == "dm" and audience_type == "dm":
            members = []
        if (
            not isinstance(audience_id, str)
            or not isinstance(audience_type, str)
            or not isinstance(members, list)
            or not all(isinstance(member, str) for member in members)
        ):
            raise sqlite3.DatabaseError("输出受众配置损坏")
        audiences[audience_id] = {
            "audience_type": audience_type,
            "members": members,
        }
    return audiences
