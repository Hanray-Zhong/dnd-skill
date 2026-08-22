from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
import sys
from typing import Any

from dnd_5e.campaign_start.session_zero import complete_session_zero
from dnd_5e.catalog import public_skill_catalog
from dnd_5e.errors import FacadeError
from dnd_5e.rules import RulesLibrary
from dnd_5e.state.types import (
    READY_TO_PLAY,
    CampaignConfigUpdate,
    CampaignSummary,
    SessionZeroCompletion,
)
from dnd_5e.workspace import (
    configure_campaign_difficulty,
    create_campaign,
    open_campaign,
)


def _reject_nonstandard_json_constant(value: str) -> None:
    raise ValueError(f"不支持的 JSON 常量：{value}")


def _json_object(value: str, *, label: str) -> dict[str, object]:
    try:
        parsed: Any = json.loads(
            value,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise argparse.ArgumentTypeError(f"{label}不是有效 JSON：{error}") from error
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError(f"{label}必须是 JSON object")
    return parsed


def _initial_config(value: str) -> dict[str, object]:
    return _json_object(value, label="初始配置")


def _session_zero_configuration(value: str) -> dict[str, object]:
    return _json_object(value, label="Session Zero 配置")


def _positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("查询上限必须是正整数") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("查询上限必须是正整数")
    return parsed


def _report_error(error: FacadeError) -> int:
    error_payload: dict[str, object] = {
        "code": error.code,
        "message": error.message,
    }
    if error.details is not None:
        error_payload["details"] = error.details
    print(
        json.dumps(
            {
                "ok": False,
                "error": error_payload,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=sys.stderr,
    )
    return 2


def _campaign_success_payload(
    operation: str,
    workspace: Path,
    summary: CampaignSummary,
) -> dict[str, object]:
    ready_to_play = summary.campaign_status == READY_TO_PLAY
    continuation = {
        "allowed": True,
        "next_step": "start_session" if ready_to_play else "session_zero",
        "ready_to_play": ready_to_play,
    }
    payload: dict[str, object] = {
        "ok": True,
        "operation": operation,
        "campaign_id": summary.campaign_id,
        "revision": summary.revision,
        "campaign_status": summary.campaign_status,
        "continuation": continuation,
        "initial_config": summary.initial_config,
        "workspace": str(workspace.resolve(strict=False)),
    }
    if summary.audiences:
        payload["audiences"] = summary.audiences
    return payload


def _config_update_success_payload(
    workspace: Path,
    update: CampaignConfigUpdate,
) -> dict[str, object]:
    payload = _campaign_success_payload("configure", workspace, update.summary)
    payload["transaction"] = {
        "audience_id": update.request.audience_id,
        "event_id": update.event_id,
        "expected_changes": {"difficulty": update.request.difficulty},
        "idempotency_key": update.request.idempotency_key,
        "replayed": update.replayed,
        "source": update.request.source,
    }
    return payload


def _session_zero_success_payload(
    workspace: Path,
    completion: SessionZeroCompletion,
) -> dict[str, object]:
    payload = _campaign_success_payload(
        "session-zero",
        workspace,
        completion.summary,
    )
    payload["transaction"] = {
        "audience_id": completion.request.audience_id,
        "event_id": completion.event_id,
        "expected_changes": {
            "audiences": completion.request.audiences,
            "campaign_status": READY_TO_PLAY,
            "session_zero": completion.request.configuration,
        },
        "idempotency_key": completion.request.idempotency_key,
        "replayed": completion.replayed,
        "source": completion.request.source,
    }
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dnd-5e")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("list-skills", help="列出第一版公开 Skill 清单")
    create_parser = subcommands.add_parser("create", help="在新建目录创建空战役")
    create_parser.add_argument("workspace", type=Path, help="新战役工作区")
    create_parser.add_argument(
        "--initial-config",
        type=_initial_config,
        default=None,
        help="需要保存在权威状态中的 JSON object",
    )
    open_parser = subcommands.add_parser("open", help="打开已有战役")
    open_parser.add_argument("workspace", type=Path, help="既有战役工作区")
    configure_parser = subcommands.add_parser(
        "configure",
        help="修改一项 Session Zero 战役配置",
    )
    configure_parser.add_argument("workspace", type=Path, help="既有战役工作区")
    configure_parser.add_argument(
        "--expected-revision",
        type=int,
        required=True,
        help="状态变更请求依据的当前修订号",
    )
    configure_parser.add_argument(
        "--idempotency-key",
        required=True,
        help="用于安全重试的稳定幂等键",
    )
    configure_parser.add_argument(
        "--difficulty",
        required=True,
        help="新的难度策略",
    )
    session_zero_parser = subcommands.add_parser(
        "session-zero",
        help="确认完整 Session Zero 配置并进入可开团状态",
    )
    session_zero_parser.add_argument("workspace", type=Path, help="既有战役工作区")
    session_zero_parser.add_argument(
        "--expected-revision",
        type=int,
        required=True,
        help="状态变更请求依据的当前修订号",
    )
    session_zero_parser.add_argument(
        "--idempotency-key",
        required=True,
        help="用于安全重试的稳定幂等键",
    )
    session_zero_parser.add_argument(
        "--configuration",
        type=_session_zero_configuration,
        required=True,
        help="完整且已经全员确认的 Session Zero JSON object",
    )
    rules_query = subcommands.add_parser("rules-query", help="定向查询固定规则章节库")
    rules_query.add_argument("--library", type=Path, default=None)
    query_kind = rules_query.add_mutually_exclusive_group(required=True)
    query_kind.add_argument("--id")
    query_kind.add_argument("--alias")
    query_kind.add_argument("--topic")
    rules_query.add_argument(
        "--general-rule-id",
        help="规则库已复核例外声明中被具体实体覆盖的一般默认规则稳定标识",
    )
    rules_query.add_argument("--limit", type=_positive_integer, default=20)
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = build_parser().parse_args(arguments)
    if options.command == "list-skills":
        print(
            json.dumps(
                {"ok": True, "skills": public_skill_catalog()},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if options.command == "create":
        initial_config = options.initial_config or {}
        try:
            summary = create_campaign(options.workspace, initial_config)
        except FacadeError as error:
            return _report_error(error)
        print(
            json.dumps(
                _campaign_success_payload("create", options.workspace, summary),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if options.command == "open":
        try:
            summary = open_campaign(options.workspace)
        except FacadeError as error:
            return _report_error(error)
        print(
            json.dumps(
                _campaign_success_payload("open", options.workspace, summary),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if options.command == "configure":
        try:
            update = configure_campaign_difficulty(
                options.workspace,
                expected_revision=options.expected_revision,
                idempotency_key=options.idempotency_key,
                difficulty=options.difficulty,
            )
        except FacadeError as error:
            return _report_error(error)
        print(
            json.dumps(
                _config_update_success_payload(options.workspace, update),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if options.command == "session-zero":
        try:
            completion = complete_session_zero(
                options.workspace,
                expected_revision=options.expected_revision,
                idempotency_key=options.idempotency_key,
                configuration=options.configuration,
            )
        except FacadeError as error:
            return _report_error(error)
        print(
            json.dumps(
                _session_zero_success_payload(options.workspace, completion),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    if options.command == "rules-query":
        query_values = {
            "id": options.id,
            "alias": options.alias,
            "topic": options.topic,
        }
        query_kind, query_value = next(
            (kind, value)
            for kind, value in query_values.items()
            if isinstance(value, str)
        )
        try:
            library = RulesLibrary(options.library)
            general_rules: list[dict[str, object]] = []
            resolution: dict[str, object] | None = None
            if options.general_rule_id is None:
                rules = library.query(
                    kind=query_kind,
                    value=query_value,
                    limit=options.limit,
                )
            else:
                entity, general_rule, resolution = (
                    library.resolve_specific_exception(
                        entity_kind=query_kind,
                        entity_value=query_value,
                        general_rule_id=options.general_rule_id,
                    )
                )
                rules = [entity]
                general_rules = [general_rule]
        except FacadeError as error:
            return _report_error(error)
        payload: dict[str, object] = {
            "ok": True,
            "query": {"kind": query_kind, "value": query_value},
            "library": {
                "version": library.version,
                "sha256": library.sha256,
            },
            "rules": rules,
        }
        if resolution is not None:
            payload["general_rules"] = general_rules
            payload["resolution"] = resolution
        print(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    raise AssertionError(f"未处理的命令：{options.command}")
