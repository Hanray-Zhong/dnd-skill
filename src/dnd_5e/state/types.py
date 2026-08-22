from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, TypeAlias, TypedDict


FailurePoint = Literal["after_event", "before_commit", "after_commit"]
FailureInjector = Callable[[FailurePoint], None]
AWAITING_SESSION_ZERO = "awaiting_session_zero"
READY_TO_PLAY = "ready_to_play"


class AudienceDefinition(TypedDict):
    audience_type: str
    members: list[str]


AudienceMap: TypeAlias = dict[str, AudienceDefinition]


@dataclass(frozen=True)
class CampaignSummary:
    campaign_id: str
    created_at: str
    revision: int
    campaign_status: str
    initial_config: dict[str, object]
    audiences: AudienceMap = field(default_factory=dict)


@dataclass(frozen=True)
class CampaignConfigRequest:
    expected_revision: int
    idempotency_key: str
    difficulty: str
    source: str
    audience_id: str


@dataclass(frozen=True)
class CampaignConfigUpdate:
    summary: CampaignSummary
    event_id: str
    request: CampaignConfigRequest
    replayed: bool


@dataclass(frozen=True)
class SessionZeroRequest:
    expected_revision: int
    idempotency_key: str
    configuration: dict[str, object]
    audiences: AudienceMap
    source: str
    audience_id: str


@dataclass(frozen=True)
class SessionZeroCompletion:
    summary: CampaignSummary
    event_id: str
    request: SessionZeroRequest
    replayed: bool


class RevisionConflict(Exception):
    def __init__(self, current: CampaignSummary) -> None:
        super().__init__("状态变更请求基于过期修订。")
        self.current = current


class IdempotencyConflict(Exception):
    pass


class InvalidStateRequest(Exception):
    pass
