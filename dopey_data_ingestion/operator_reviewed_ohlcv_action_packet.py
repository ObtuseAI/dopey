"""Build human-readable operator action packets for reviewed OHLCV reruns."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .local_staging_contract import REPO_ROOT
from .operator_reviewed_ohlcv_stage_models import (
    OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
    OperatorReviewedOhlcvActionPacket,
)


ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "operator_reviewed_ohlcv_stage"
ACTION_PACKET_JSON_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_action_packet.json"
ACTION_PACKET_MD_PATH = ARTIFACT_DIR / "operator_reviewed_ohlcv_action_packet.md"
REQUIRED_HEADER = "date,symbol,open,high,low,close,adjusted_close,volume,source"


def write_operator_reviewed_ohlcv_action_packet(summary: dict[str, Any]) -> dict[str, Any]:
    repair_groups = _repair_groups(summary)
    required_actions = _required_actions(summary)
    packet = OperatorReviewedOhlcvActionPacket(
        artifact_type="operator_reviewed_ohlcv_action_packet",
        stage_version=OPERATOR_REVIEWED_OHLCV_STAGE_VERSION,
        packet_id="operator-reviewed-ohlcv-action-packet-v1",
        packet_status=_packet_status(summary),
        operator_reviewed_stage_decision=str(summary.get("operator_reviewed_stage_decision", "operator_must_stage_reviewed_files")),
        required_actions=required_actions,
        blocked_items=_blocked_items(),
        repair_groups=repair_groups,
        run_command="python -m dopey_data_ingestion.run_operator_reviewed_ohlcv_stage_rerun",
        paper_only=True,
        live_blocked=True,
        network_fetch_performed=False,
        credentials_created=False,
        env_created=False,
        broker_connection_used=False,
        strategy_promotion_allowed=False,
        not_options_evidence=True,
        not_profitability_claim=True,
        not_live_ready=True,
        packet_hash="",
    ).to_dict()
    _write_json(ACTION_PACKET_JSON_PATH, packet)
    ACTION_PACKET_MD_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTION_PACKET_MD_PATH.write_text(_render_markdown(summary, packet), encoding="utf-8")
    return {**packet, "json_path": str(ACTION_PACKET_JSON_PATH), "markdown_path": str(ACTION_PACKET_MD_PATH)}


def _packet_status(summary: dict[str, Any]) -> str:
    if summary.get("operator_reviewed_stage_status") == "terminal_block":
        return "terminal_block"
    if summary.get("operator_reviewed_stage_decision") == "real_ohlcv_signal_evidence_ready_no_promotion":
        return "validation_passed_no_promotion"
    return "operator_action_required"


def _required_actions(summary: dict[str, Any]) -> list[str]:
    if int(summary.get("staged_file_count", 0)) == 0:
        return [
            "Place reviewed CSV or JSONL files under dopey_data/real/raw/daily_ohlcv/.",
            "Optionally place reviewed market context files under dopey_data/real/raw/market_context/.",
            "Optionally place reviewed corporate actions files under dopey_data/real/raw/corporate_actions/.",
            "Complete dopey_data/real/manifests/operator_ohlcv_source_review.json.",
            "Run python -m dopey_data_ingestion.run_operator_reviewed_ohlcv_stage_rerun.",
        ]
    if summary.get("source_review_status") != "operator_review_packet_valid":
        return ["Complete the operator source-review packet before final manifest readiness can pass."]
    if summary.get("final_manifest_status") != "final_manifest_ready_for_validator":
        return ["Manually review candidate manifest and complete dopey_data/real/manifests/real_data_manifest.json."]
    if summary.get("local_ohlcv_status") != "local_ohlcv_validation_pass":
        return ["Repair local OHLCV validator failures and rerun the reviewed stage-rerun command."]
    if summary.get("history_spine_activation_status") != "real_ohlcv_history_spine_activation_pass":
        return ["Repair history spine activation blockers and rerun."]
    return ["Proceed to real OHLCV signal backtester work without strategy promotion."]


def _repair_groups(summary: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "source_review_packet_repairs": [] if summary.get("source_review_status") == "operator_review_packet_valid" else ["Complete all required source, terms, license, provenance, and affirmation fields."],
        "manifest_repairs": [] if summary.get("final_manifest_status") == "final_manifest_ready_for_validator" else ["Complete final manifest; draft and candidate manifests are not evidence."],
        "schema_repairs": ["Use required daily OHLCV header: " + REQUIRED_HEADER],
        "quality_repairs": ["Remove future dates, duplicate symbol/date rows, invalid OHLC ranges, negative volume, and missing source values."],
        "license_provenance_repairs": ["Record reviewed license status, provider terms, provenance notes, source references, and export dates."],
        "hash_repairs": ["Regenerate local hashes from staged files and copy matching hashes into the final manifest."],
        "sample_template_contamination_repairs": ["Remove SAMPLE_ONLY, sample_only=true, not_real_data=true, templates, and fixtures from real raw folders."],
        "credential_live_marker_removal": ["Remove .env, API keys, tokens, broker exports, live order records, account balances, buying power, real sizing, scheduler, and daemon markers."],
        "manual_review_requirements": ["Operator must manually review data files, source terms, final manifest, and all validation outputs."],
    }


def _blocked_items() -> list[str]:
    return [
        ".env",
        "API keys",
        "tokens",
        "broker exports",
        "live order records",
        "account balances",
        "buying power",
        "real sizing",
        "sample rows",
        "SAMPLE_ONLY",
        "sample_only=true",
        "not_real_data=true",
        "curl",
        "wget",
        "Alpha Vantage",
        "broker commands",
    ]


def _render_markdown(summary: dict[str, Any], packet: dict[str, Any]) -> str:
    lines = [
        "# DOPEY Operator Reviewed OHLCV Stage Rerun Action Packet",
        "",
        "## Current State",
        f"- operator_reviewed_stage_status: `{summary.get('operator_reviewed_stage_status', 'missing')}`",
        f"- operator_reviewed_stage_decision: `{summary.get('operator_reviewed_stage_decision', 'missing')}`",
        f"- source_review_status: `{summary.get('source_review_status', 'missing')}`",
        f"- staged_file_count: `{summary.get('staged_file_count', 0)}`",
        f"- final_manifest_status: `{summary.get('final_manifest_status', 'missing')}`",
        f"- local_ohlcv_status: `{summary.get('local_ohlcv_status', 'missing')}`",
        f"- history_spine_activation_status: `{summary.get('history_spine_activation_status', 'missing')}`",
        f"- real_signal_validation_status: `{summary.get('real_signal_validation_status', 'missing')}`",
        "",
        "## Required Operator Actions",
    ]
    for action in packet["required_actions"]:
        lines.append(f"- {action}")
    lines.extend([
        "",
        "## Approved Local Folders",
        "- `dopey_data/real/raw/daily_ohlcv/`",
        "- `dopey_data/real/raw/market_context/`",
        "- `dopey_data/real/raw/corporate_actions/`",
        "",
        "## Required Daily OHLCV Header",
        "```csv",
        REQUIRED_HEADER,
        "```",
        "",
        "## Source Review Packet",
        "- Complete `dopey_data/real/manifests/operator_ohlcv_source_review.json`.",
        "- Source review is required; source name, URL, or filename never implies approval.",
        "",
        "## Do Not Include",
    ])
    for blocked in _blocked_items():
        lines.append(f"- `{blocked}`")
    lines.extend([
        "",
        "## Run",
        "```powershell",
        "python -m dopey_data_ingestion.run_operator_reviewed_ohlcv_stage_rerun",
        "```",
        "",
        "## Evidence Boundaries",
        "- Draft manifest is not evidence.",
        "- Candidate manifest is not evidence.",
        "- Final manifest must pass validation.",
        "- OHLCV is not options evidence.",
        "- Validation pass is not strategy promotion.",
        "- Validation pass is not profitability.",
        "- Validation pass is not live readiness.",
        "- No network fetch, scrape, credentials, broker connection, or Alpha Vantage path is allowed.",
    ])
    if summary.get("operator_reviewed_stage_decision") == "real_ohlcv_signal_evidence_ready_no_promotion":
        lines.extend([
            "",
            "## Passed Gates",
            f"- validator_status: `{summary.get('local_ohlcv_status', 'missing')}`",
            f"- history_activation_status: `{summary.get('history_spine_activation_status', 'missing')}`",
            f"- real_signal_validation_status: `{summary.get('real_signal_validation_status', 'missing')}`",
            "- promotion: `blocked`",
            f"- next_target: `{summary.get('next_recommended_target', '')}`",
        ])
    return "\n".join(lines) + "\n"


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
