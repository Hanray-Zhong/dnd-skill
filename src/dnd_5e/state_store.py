from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from dnd_5e.state.audiences import read_audiences
from dnd_5e.state.encoding import canonical_json
from dnd_5e.state.formulas import read_derived_values
from dnd_5e.state.types import (
    AWAITING_SESSION_ZERO,
    CampaignConfigRequest,
    CampaignConfigUpdate,
    CampaignSummary,
    FailureInjector,
    IdempotencyConflict,
    READY_TO_PLAY,
    RevisionConflict,
)


STATE_SCHEMA_NUMBER = 2
STATE_SCHEMA_VERSION = str(STATE_SCHEMA_NUMBER)
STATE_APPLICATION_ID = int.from_bytes(b"DND5", byteorder="big")
INITIAL_CAMPAIGN_STATUS = AWAITING_SESSION_ZERO
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
    ("table", "state_requests"): """
        CREATE TABLE state_requests (
            idempotency_key TEXT PRIMARY KEY,
            request_json TEXT NOT NULL,
            base_revision INTEGER NOT NULL REFERENCES revisions(revision),
            committed_revision INTEGER NOT NULL REFERENCES revisions(revision),
            event_id TEXT NOT NULL UNIQUE REFERENCES events(event_id),
            result_json TEXT NOT NULL
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


def initialize_state_store(
    database_path: Path,
    *,
    campaign_id: str,
    event_id: str,
    created_at: str,
    initial_config: dict[str, object],
) -> CampaignSummary:
    canonical_config = canonical_json(initial_config)
    entity_payload = canonical_json(
        {
            "campaign_status": INITIAL_CAMPAIGN_STATUS,
            "initial_config": initial_config,
        }
    )
    event_payload = canonical_json(
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
                ("dm", "dm", canonical_json({"members": []})),
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
        audiences={
            "dm": {
                "audience_type": "dm",
                "members": [],
            }
        },
    )


def update_campaign_difficulty(
    database_path: Path,
    *,
    request: CampaignConfigRequest,
    event_id: str,
    committed_at: str,
    failure_injector: FailureInjector | None = None,
) -> CampaignConfigUpdate:
    request_json = canonical_json(
        {
            "audience_id": request.audience_id,
            "expected_changes": {"difficulty": request.difficulty},
            "expected_revision": request.expected_revision,
            "operation": "configure_difficulty",
            "source": request.source,
        }
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        try:
            existing_request = connection.execute(
                """
                SELECT request_json, event_id, result_json
                FROM state_requests
                WHERE idempotency_key = ?
                """,
                (request.idempotency_key,),
            ).fetchone()
            if existing_request is not None:
                stored_request, stored_event_id, stored_result = existing_request
                if stored_request != request_json:
                    raise IdempotencyConflict
                result_payload = json.loads(stored_result)
                if not isinstance(result_payload, dict):
                    raise sqlite3.DatabaseError("幂等请求结果损坏")
                stored_campaign_id = result_payload.get("campaign_id")
                stored_created_at = result_payload.get("created_at")
                stored_config = result_payload.get("initial_config")
                stored_revision = result_payload.get("revision")
                stored_status = result_payload.get("campaign_status")
                if (
                    not isinstance(stored_campaign_id, str)
                    or not isinstance(stored_created_at, str)
                    or not isinstance(stored_config, dict)
                    or type(stored_revision) is not int
                    or stored_status != INITIAL_CAMPAIGN_STATUS
                ):
                    raise sqlite3.DatabaseError("幂等请求结果损坏")
                replayed_result = CampaignConfigUpdate(
                    summary=CampaignSummary(
                        campaign_id=stored_campaign_id,
                        created_at=stored_created_at,
                        revision=stored_revision,
                        campaign_status=stored_status,
                        initial_config=stored_config,
                    ),
                    event_id=str(stored_event_id),
                    request=request,
                    replayed=True,
                )
                connection.rollback()
                return replayed_result

            metadata = connection.execute(
                """
                SELECT metadata.campaign_id,
                       metadata.created_at,
                       metadata.current_revision,
                       campaign.payload_json
                FROM campaign_metadata AS metadata
                JOIN entities AS campaign
                  ON campaign.entity_id = metadata.campaign_id
                 AND campaign.entity_type = 'campaign'
                 AND campaign.revision = metadata.current_revision
                WHERE metadata.singleton = 1
                """
            ).fetchone()
            if metadata is None:
                raise sqlite3.DatabaseError(
                    "战役状态库缺少一致的 campaign 当前修订"
                )
            campaign_id, created_at, current_revision, campaign_payload = metadata
            payload = json.loads(campaign_payload)
            initial_config = (
                payload.get("initial_config") if isinstance(payload, dict) else None
            )
            campaign_status = (
                payload.get("campaign_status") if isinstance(payload, dict) else None
            )
            if (
                not isinstance(initial_config, dict)
                or campaign_status != INITIAL_CAMPAIGN_STATUS
            ):
                raise sqlite3.DatabaseError(
                    "campaign 实体缺少初始配置或战役状态"
                )
            current = CampaignSummary(
                campaign_id=str(campaign_id),
                created_at=str(created_at),
                revision=int(current_revision),
                campaign_status=campaign_status,
                initial_config=initial_config,
            )
            if current.revision != request.expected_revision:
                raise RevisionConflict(current)

            updated_config = {**initial_config, "difficulty": request.difficulty}
            new_revision = current.revision + 1
            updated_payload = canonical_json(
                {
                    "campaign_status": campaign_status,
                    "initial_config": updated_config,
                }
            )
            event_payload = canonical_json(
                {
                    "campaign_id": current.campaign_id,
                    "changes": {
                        "difficulty": {
                            "after": request.difficulty,
                            "before": initial_config.get("difficulty"),
                        }
                    },
                    "expected_revision": request.expected_revision,
                }
            )
            result = CampaignSummary(
                campaign_id=current.campaign_id,
                created_at=current.created_at,
                revision=new_revision,
                campaign_status=campaign_status,
                initial_config=updated_config,
            )
            result_json = canonical_json(
                {
                    "campaign_id": result.campaign_id,
                    "campaign_status": result.campaign_status,
                    "created_at": result.created_at,
                    "initial_config": result.initial_config,
                    "revision": result.revision,
                }
            )

            connection.execute(
                "INSERT INTO revisions VALUES (?, ?, ?)",
                (new_revision, committed_at, "dnd-5e-campaign-state"),
            )
            updated_rows = connection.execute(
                """
                UPDATE entities
                SET revision = ?, payload_json = ?
                WHERE entity_id = ?
                  AND entity_type = 'campaign'
                  AND revision = ?
                """,
                (
                    new_revision,
                    updated_payload,
                    current.campaign_id,
                    current.revision,
                ),
            ).rowcount
            if updated_rows != 1:
                raise sqlite3.DatabaseError("campaign 当前实体更新失败")
            connection.execute(
                "UPDATE campaign_metadata SET current_revision = ? WHERE singleton = 1",
                (new_revision,),
            )
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    new_revision,
                    1,
                    "campaign_config_updated",
                    request.source,
                    request.audience_id,
                    event_payload,
                ),
            )
            if failure_injector is not None:
                failure_injector("after_event")
            connection.execute(
                "INSERT INTO state_requests VALUES (?, ?, ?, ?, ?, ?)",
                (
                    request.idempotency_key,
                    request_json,
                    current.revision,
                    new_revision,
                    event_id,
                    result_json,
                ),
            )
            if failure_injector is not None:
                failure_injector("before_commit")
            connection.commit()
            if failure_injector is not None:
                failure_injector("after_commit")
        except BaseException:
            connection.rollback()
            raise

    return CampaignConfigUpdate(
        summary=result,
        event_id=event_id,
        request=request,
        replayed=False,
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

        audiences = read_audiences(connection)
        derived_values = read_derived_values(connection)

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
        or campaign_status not in {INITIAL_CAMPAIGN_STATUS, READY_TO_PLAY}
    ):
        raise sqlite3.DatabaseError("campaign 实体缺少初始配置或战役状态")
    return CampaignSummary(
        campaign_id=str(campaign_id),
        created_at=str(created_at),
        revision=int(revision),
        campaign_status=campaign_status,
        initial_config=initial_config,
        audiences=audiences,
        derived_values=derived_values,
    )
