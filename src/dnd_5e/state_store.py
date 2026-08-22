from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3


STATE_SCHEMA_NUMBER = 1
STATE_SCHEMA_VERSION = str(STATE_SCHEMA_NUMBER)
STATE_APPLICATION_ID = int.from_bytes(b"DND5", byteorder="big")
INITIAL_CAMPAIGN_STATUS = "awaiting_session_zero"
_STATE_SCHEMA_SQL = {
    ("table", "revisions"): """
        CREATE TABLE revisions (
            revision INTEGER PRIMARY KEY,
            committed_at TEXT NOT NULL,
            source TEXT NOT NULL
        ) STRICT
    """,
    ("table", "campaign_metadata"): """
        CREATE TABLE campaign_metadata (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            campaign_id TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            current_revision INTEGER NOT NULL REFERENCES revisions(revision)
        ) STRICT
    """,
    ("table", "audiences"): """
        CREATE TABLE audiences (
            audience_id TEXT PRIMARY KEY,
            audience_type TEXT NOT NULL,
            definition_json TEXT NOT NULL
        ) STRICT
    """,
    ("table", "entities"): """
        CREATE TABLE entities (
            entity_id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            revision INTEGER NOT NULL REFERENCES revisions(revision),
            payload_json TEXT NOT NULL
        ) STRICT
    """,
    ("table", "events"): """
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY,
            revision INTEGER NOT NULL REFERENCES revisions(revision),
            event_sequence INTEGER NOT NULL CHECK (event_sequence > 0),
            event_type TEXT NOT NULL,
            source TEXT NOT NULL,
            audience_id TEXT NOT NULL REFERENCES audiences(audience_id),
            payload_json TEXT NOT NULL,
            UNIQUE (revision, event_sequence)
        ) STRICT
    """,
    ("table", "knowledge"): """
        CREATE TABLE knowledge (
            subject_id TEXT NOT NULL,
            fact_id TEXT NOT NULL,
            knowledge_state TEXT NOT NULL,
            revision INTEGER NOT NULL REFERENCES revisions(revision),
            payload_json TEXT NOT NULL,
            PRIMARY KEY (subject_id, fact_id)
        ) STRICT
    """,
    ("index", "entities_by_type"): (
        "CREATE INDEX entities_by_type ON entities(entity_type)"
    ),
    ("index", "events_by_type"): "CREATE INDEX events_by_type ON events(event_type)",
    ("index", "knowledge_by_fact"): (
        "CREATE INDEX knowledge_by_fact ON knowledge(fact_id)"
    ),
}
STATE_SCHEMA_STATEMENTS = tuple(_STATE_SCHEMA_SQL.values())
STATE_SCHEMA_DEFINITIONS = {
    key: " ".join(statement.split())
    for key, statement in _STATE_SCHEMA_SQL.items()
}
STATE_SCHEMA_OBJECTS = frozenset(STATE_SCHEMA_DEFINITIONS)


@dataclass(frozen=True)
class CampaignSummary:
    campaign_id: str
    created_at: str
    revision: int
    campaign_status: str
    initial_config: dict[str, object]


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def initialize_state_store(
    database_path: Path,
    *,
    campaign_id: str,
    event_id: str,
    created_at: str,
    initial_config: dict[str, object],
) -> CampaignSummary:
    canonical_config = _canonical_json(initial_config)
    entity_payload = _canonical_json(
        {
            "campaign_status": INITIAL_CAMPAIGN_STATUS,
            "initial_config": initial_config,
        }
    )
    event_payload = _canonical_json(
        {
            "campaign_id": campaign_id,
            "campaign_status": INITIAL_CAMPAIGN_STATUS,
            "initial_config": initial_config,
        }
    )

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(f"PRAGMA application_id = {STATE_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {STATE_SCHEMA_NUMBER}")
            for statement in STATE_SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO revisions VALUES (?, ?, ?)",
                (1, created_at, "dnd-5e-campaign-start"),
            )
            connection.execute(
                "INSERT INTO campaign_metadata VALUES (?, ?, ?, ?)",
                (1, campaign_id, created_at, 1),
            )
            connection.execute(
                "INSERT INTO audiences VALUES (?, ?, ?)",
                ("dm", "dm", "{}"),
            )
            connection.execute(
                "INSERT INTO entities VALUES (?, ?, ?, ?, ?)",
                (campaign_id, "campaign", 1, 1, entity_payload),
            )
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    1,
                    1,
                    "campaign_created",
                    "dnd-5e-campaign-start",
                    "dm",
                    event_payload,
                ),
            )
            connection.commit()
        except BaseException:
            connection.rollback()
            raise

    return CampaignSummary(
        campaign_id=campaign_id,
        created_at=created_at,
        revision=1,
        campaign_status=INITIAL_CAMPAIGN_STATUS,
        initial_config=json.loads(canonical_config),
    )


def read_state_store(database_path: Path) -> CampaignSummary:
    database_uri = f"{database_path.resolve().as_uri()}?mode=ro"
    with sqlite3.connect(database_uri, uri=True) as connection:
        connection.execute("PRAGMA query_only = ON")
        connection.execute("PRAGMA foreign_keys = ON")
        integrity_rows = connection.execute("PRAGMA quick_check").fetchall()
        if integrity_rows != [("ok",)]:
            raise sqlite3.DatabaseError(f"SQLite 完整性检查失败：{integrity_rows}")
        application_id = connection.execute("PRAGMA application_id").fetchone()
        schema_version = connection.execute("PRAGMA user_version").fetchone()
        if application_id != (STATE_APPLICATION_ID,) or schema_version != (
            STATE_SCHEMA_NUMBER,
        ):
            raise sqlite3.DatabaseError("战役状态库标识或 schema 版本不匹配")

        schema_definitions = {
            (object_type, name): " ".join(definition.split())
            for object_type, name, definition in connection.execute(
                """
                SELECT type, name, sql
                FROM sqlite_schema
                WHERE name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
            if isinstance(definition, str)
        }
        if schema_definitions != STATE_SCHEMA_DEFINITIONS:
            raise sqlite3.DatabaseError(
                f"战役状态库 schema 不匹配：{sorted(schema_definitions)}"
            )
        foreign_key_violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_violations:
            raise sqlite3.DatabaseError(
                f"战役状态库外键损坏：{foreign_key_violations}"
            )

        metadata = connection.execute(
            """
            SELECT metadata.campaign_id,
                   metadata.created_at,
                   metadata.current_revision,
                   campaign.payload_json
            FROM campaign_metadata AS metadata
            JOIN revisions AS current_revision
              ON current_revision.revision = metadata.current_revision
            JOIN entities AS campaign
              ON campaign.entity_id = metadata.campaign_id
             AND campaign.entity_type = 'campaign'
             AND campaign.revision = metadata.current_revision
            WHERE metadata.singleton = 1
            """
        ).fetchone()
        if metadata is None:
            raise sqlite3.DatabaseError("战役状态库缺少一致的 campaign 当前修订")
        campaign_id, created_at, revision, campaign_payload = metadata
        revision_without_event = connection.execute(
            """
            SELECT revisions.revision
            FROM revisions
            LEFT JOIN events ON events.revision = revisions.revision
            WHERE events.event_id IS NULL
            LIMIT 1
            """
        ).fetchone()
        if revision_without_event is not None:
            raise sqlite3.DatabaseError(
                f"修订 {revision_without_event[0]} 缺少不可变事件"
            )

    payload = json.loads(campaign_payload)
    initial_config = payload.get("initial_config") if isinstance(payload, dict) else None
    campaign_status = payload.get("campaign_status") if isinstance(payload, dict) else None
    if (
        not isinstance(initial_config, dict)
        or campaign_status != INITIAL_CAMPAIGN_STATUS
    ):
        raise sqlite3.DatabaseError("campaign 实体缺少初始配置或战役状态")
    return CampaignSummary(
        campaign_id=str(campaign_id),
        created_at=str(created_at),
        revision=int(revision),
        campaign_status=campaign_status,
        initial_config=initial_config,
    )
