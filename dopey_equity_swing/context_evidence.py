"""Evidence gate for cross-asset and news context influence."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


CONTEXT_EVIDENCE_POLICY_VERSION = "dopey-context-evidence-v2"
CALENDAR_DURATION_GATE_ENABLED = False
CALENDAR_DURATION_GATE_AUTHORITY = "creator_directive_2026-07-13"
SNAPSHOT_HISTORY_ROLE = "provenance_and_research_telemetry_not_readiness_duration_gate"
MINIMUM_WALK_FORWARD_ERAS = 3
MINIMUM_RESOLVED_DECISIONS = 200


def build_context_evidence_gate(
    cross_asset_snapshot_root: Path,
    news_snapshot_root: Path,
    news_event_ledger_path: Path,
    context_decision_ledger_path: Path,
    context_outcome_ledger_path: Path,
) -> dict[str, Any]:
    cross_snapshots = _complete_snapshots(
        cross_asset_snapshot_root,
        "cross_asset_daily.csv",
        "cross_asset_context_manifest.json",
        "dataset_status",
    )
    news_snapshots = _complete_snapshots(
        news_snapshot_root,
        "news_events.jsonl",
        "news_context_manifest.json",
        "pipeline_status",
    )
    cross_days = {_snapshot_day(path) for path in cross_snapshots}
    news_days = {_snapshot_day(path) for path in news_snapshots}
    joint_days = sorted(cross_days & news_days)
    ledger_events = _ledger_record_count(news_event_ledger_path, "event_id")
    decision_records = _ledger_record_count(context_decision_ledger_path, "decision_id")
    outcome_records = _ledger_record_count(context_outcome_ledger_path, "decision_id")
    pending_records = max(decision_records - outcome_records, 0)
    if outcome_records < MINIMUM_RESOLVED_DECISIONS:
        status = "blocked_insufficient_resolved_context_decisions"
    else:
        status = "blocked_pending_purged_walk_forward_validation"
    return {
        "artifact_type": "external_context_evidence_gate",
        "context_evidence_policy_version": CONTEXT_EVIDENCE_POLICY_VERSION,
        "evidence_status": status,
        "cross_asset_snapshot_count": len(cross_snapshots),
        "news_snapshot_count": len(news_snapshots),
        "joint_snapshot_day_count": len(joint_days),
        "first_joint_snapshot_day": joint_days[0] if joint_days else None,
        "last_joint_snapshot_day": joint_days[-1] if joint_days else None,
        "news_event_ledger_count": ledger_events,
        "context_decision_ledger_count": decision_records,
        "context_outcome_ledger_count": outcome_records,
        "pending_context_decision_count": pending_records,
        "resolved_context_decision_fraction": round(outcome_records / decision_records, 6) if decision_records else 0.0,
        "calendar_duration_gate_enabled": CALENDAR_DURATION_GATE_ENABLED,
        "calendar_duration_gate_authority": CALENDAR_DURATION_GATE_AUTHORITY,
        "minimum_snapshot_days": None,
        "snapshot_history_role": SNAPSHOT_HISTORY_ROLE,
        "minimum_walk_forward_eras": MINIMUM_WALK_FORWARD_ERAS,
        "minimum_resolved_decisions": MINIMUM_RESOLVED_DECISIONS,
        "positive_context_promotion_allowed": False,
        "context_sizing_allowed": False,
        "defensive_veto_allowed": True,
        "required_next_evidence": (
            "resolve_200_forward_context_decisions_then_run_purged_walk_forward_ablation_across_three_eras_"
            "with_precision_drawdown_and_calibration_guardrails_while_continuing_immutable_as_of_snapshots"
        ),
        "paper_only": True,
        "live_blocked": True,
    }


def build_context_decision_records(
    theses: list[dict[str, Any]],
    cross_asset_regime: dict[str, Any],
    news_intelligence: dict[str, Any],
    context_evidence_gate: dict[str, Any],
    recorded_at: str,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for thesis in theses:
        context = dict(thesis.get("external_context", {}))
        if context.get("original_equity_trade_intent") not in {"long_call", "long_put"}:
            continue
        if int(thesis.get("expected_hold_trading_days") or 0) < 1:
            continue
        decision_key_payload = {
            "symbol": thesis["symbol"],
            "market_as_of": thesis["as_of_date"],
            "base_equity_trade_intent": context.get("original_equity_trade_intent"),
        }
        decision_id = hashlib.sha256(json.dumps(decision_key_payload, sort_keys=True).encode("utf-8")).hexdigest()
        records.append(
            {
                "artifact_type": "external_context_forward_decision",
                "decision_id": decision_id,
                "decision_key": decision_id,
                **decision_key_payload,
                "semantic_decision_scope": "eligible_symbol_session",
                "session_id": thesis["as_of_date"],
                "strategy_id": thesis.get("strategy_id"),
                "cohort_id": thesis.get("cohort_id"),
                "era_id": thesis.get("era_id"),
                "regime_id": thesis.get("regime_id"),
                "source_attribution": {
                    "cross_asset_latest_source_date": (
                        cross_asset_regime.get("latest_source_date_max")
                    ),
                    "news_decision_time": news_intelligence.get(
                        "decision_time"
                    ),
                    "context_evidence_status": context_evidence_gate.get(
                        "evidence_status"
                    ),
                },
                "equity_direction": thesis["direction"],
                "final_trade_intent": thesis["trade_intent"],
                "entry_reference_price": thesis.get("entry_reference_price"),
                "target_price": thesis.get("target_price"),
                "invalidation_price": thesis.get("invalidation_price"),
                "cross_asset_theme_score": context.get("cross_asset_theme_score"),
                "news_theme_score": context.get("news_risk_tone_score"),
                "context_confirmation_score": context.get("context_confirmation_score"),
                "systemic_stress_score": context.get("systemic_stress_score"),
                "corroborated_news_alert_present": context.get("corroborated_news_alert_present"),
                "cross_asset_latest_source_date": cross_asset_regime.get("latest_source_date_max"),
                "recorded_at": recorded_at,
                "news_decision_time": news_intelligence.get("decision_time"),
                "theme": context.get("theme"),
                "context_confidence_tier": context.get("context_confidence_tier"),
                "veto_reasons": context.get("veto_reasons", []),
                "expected_hold_trading_days": thesis.get("expected_hold_trading_days"),
                "evidence_status_at_decision": context_evidence_gate.get("evidence_status"),
                "outcome_status": "pending_forward_outcome",
                "outcome_label": None,
                "outcome_return": None,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return records


def build_context_decision_velocity(
    theses: list[dict[str, Any]],
) -> dict[str, Any]:
    eligible: list[dict[str, Any]] = []
    exclusion_counts = {
        "non_directional_or_ineligible_equity_intent": 0,
        "missing_positive_holding_horizon": 0,
    }
    for thesis in theses:
        context = thesis.get("external_context")
        original_intent = (
            context.get("original_equity_trade_intent")
            if isinstance(context, dict)
            else None
        )
        if original_intent not in {"long_call", "long_put"}:
            exclusion_counts[
                "non_directional_or_ineligible_equity_intent"
            ] += 1
            continue
        if int(thesis.get("expected_hold_trading_days") or 0) < 1:
            exclusion_counts["missing_positive_holding_horizon"] += 1
            continue
        eligible.append(thesis)
    semantic_keys = {
        (
            str(thesis.get("symbol", "")),
            str(thesis.get("as_of_date", "")),
            str(
                (
                    thesis.get("external_context")
                    if isinstance(thesis.get("external_context"), dict)
                    else {}
                ).get("original_equity_trade_intent", "")
            ),
        )
        for thesis in eligible
    }
    thesis_count = len(theses)
    return {
        "policy": "one_immutable_deduplicated_semantic_decision_per_eligible_symbol_session",
        "thesis_count": thesis_count,
        "eligible_symbol_session_count": len(eligible),
        "unique_semantic_decision_count": len(semantic_keys),
        "eligible_coverage_fraction": round(
            len(eligible) / float(thesis_count),
            8,
        )
        if thesis_count
        else 0.0,
        "exclusion_counts": exclusion_counts,
        "maturity_policy": "incremental_idempotent_trading_horizon_settlement",
        "readiness_threshold_changed": False,
        "synthetic_evidence_allowed": False,
    }


def append_context_decision_records(path: Path, records: list[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                parsed = json.loads(line)
                if not isinstance(parsed, dict) or "decision_id" not in parsed:
                    raise ValueError(f"context decision ledger row is invalid: path={path}, line={line_number}")
                existing_ids.add(str(parsed["decision_id"]))
    new_records = [record for record in records if str(record["decision_id"]) not in existing_ids]
    with path.open("a", encoding="utf-8") as handle:
        for record in new_records:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
    return len(new_records)


def repair_context_decision_ledger(path: Path) -> dict[str, int]:
    if not path.exists():
        return {"input_count": 0, "canonical_count": 0, "duplicates_removed": 0, "non_evaluable_removed": 0}
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            parsed = json.loads(line)
            if not isinstance(parsed, dict) or "decision_id" not in parsed:
                raise ValueError(f"context decision ledger row is invalid: path={path}, line={line_number}")
            records.append(parsed)
    evaluable = [
        record for record in records
        if record.get("base_equity_trade_intent") in {"long_call", "long_put"}
        and int(record.get("expected_hold_trading_days") or 0) >= 1
    ]
    canonical: dict[str, dict[str, Any]] = {}
    for record in sorted(evaluable, key=lambda item: str(item.get("recorded_at", ""))):
        key = _legacy_decision_key(record)
        if key not in canonical:
            canonical[key] = {**record, "decision_id": key, "decision_key": key}
    if len(canonical) != len(records) or any("decision_key" not in record for record in records):
        temp = path.with_suffix(".jsonl.tmp")
        payload = "\n".join(
            json.dumps(record, sort_keys=True, ensure_ascii=False)
            for record in canonical.values()
        )
        temp.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
        temp.replace(path)
    return {
        "input_count": len(records),
        "canonical_count": len(canonical),
        "duplicates_removed": len(evaluable) - len(canonical),
        "non_evaluable_removed": len(records) - len(evaluable),
    }


def _legacy_decision_key(record: dict[str, Any]) -> str:
    identity = {
        "symbol": record.get("symbol"),
        "market_as_of": record.get("market_as_of"),
        "base_equity_trade_intent": record.get("base_equity_trade_intent"),
    }
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()


def _snapshot_day(path: Path) -> str:
    stamp = path.parent.name
    if len(stamp) < 8 or not stamp[:8].isdigit():
        raise ValueError(f"snapshot directory does not start with YYYYMMDD: path={path}")
    return f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}"


def _complete_snapshots(
    root: Path,
    data_filename: str,
    manifest_filename: str,
    status_field: str,
) -> list[Path]:
    if not root.exists():
        return []
    complete: list[Path] = []
    for data_path in sorted(root.glob(f"*/{data_filename}")):
        manifest_path = data_path.parent / manifest_filename
        if not manifest_path.exists():
            continue
        parsed = json.loads(manifest_path.read_text(encoding="utf-8"))
        if str(parsed.get(status_field, "")) == "complete":
            complete.append(data_path)
    return complete


def _ledger_record_count(path: Path, identifier_field: str) -> int:
    if not path.exists():
        return 0
    event_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            parsed = json.loads(line)
            if not isinstance(parsed, dict) or identifier_field not in parsed:
                raise ValueError(
                    f"ledger row is invalid: path={path}, line={line_number}, required_field={identifier_field}"
                )
            event_ids.add(str(parsed[identifier_field]))
    return len(event_ids)
