from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


FailurePoint = Literal["after_event", "before_commit", "after_commit"]
FailureInjector = Callable[[FailurePoint], None]


@dataclass(frozen=True)
class CampaignSummary:
    campaign_id: str
    created_at: str
    revision: int
    campaign_status: str
    initial_config: dict[str, object]


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


class RevisionConflict(Exception):
    def __init__(self, current: CampaignSummary) -> None:
        super().__init__("状态变更请求基于过期修订。")
        self.current = current


class IdempotencyConflict(Exception):
    pass
