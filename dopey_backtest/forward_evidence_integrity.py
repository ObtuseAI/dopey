"""Classify forward-walk outcomes without rewriting historical evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, Literal, TypedDict

from dopey_options.liquidity_engine import ENTRY_POLICY_VERSION, EXIT_POLICY_VERSION
from dopey_research_pipeline.artifact_io import write_json_atomic, write_jsonl_atomic
from dopey_research_pipeline.quality_ledger import reproducibility_hash


REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
FORWARD_WALK_DIR: Final[Path] = REPO_ROOT / "artifacts" / "dopey" / "forward_walk"
LEDGER_PATH: Final[Path] = FORWARD_WALK_DIR / "forward_walk_ledger.json"
POLICY_REPLAY_PATH: Final[Path] = FORWARD_WALK_DIR / "trade_loss_hypotheses.json"
INTEGRITY_SUMMARY_PATH: Final[Path] = FORWARD_WALK_DIR / "forward_evidence_integrity.json"
VALIDATED_OUTCOMES_PATH: Final[Path] = FORWARD_WALK_DIR / "forward_walk_validated_closed_trades.jsonl"
CENSORED_OUTCOMES_PATH: Final[Path] = FORWARD_WALK_DIR / "forward_walk_censored_outcomes.jsonl"
QUARANTINED_OUTCOMES_PATH: Final[Path] = FORWARD_WALK_DIR / "forward_walk_quarantined_outcomes.jsonl"

INTEGRITY_VERSION: Final[str] = "dopey-forward-evidence-integrity-v1"
VALIDATED_OUTCOME: Final[str] = "validated_forward_outcome"
CENSORED_OUTCOME: Final[str] = "censored_missing_quote_continuity"
QUARANTINED_OUTCOME: Final[str] = "quarantined_legacy_policy_nonconforming"
OutcomeClass = Literal[
    "validated_forward_outcome",
    "censored_missing_quote_continuity",
    "quarantined_legacy_policy_nonconforming",
]


class PolicyReplay(TypedDict):
    entry_rejection_reasons: tuple[str, ...]
    exit_rejection_reasons: tuple[str, ...]


class ClassifiedOutcomes(TypedDict):
    validated: list[dict[str, Any]]
    censored: list[dict[str, Any]]
    quarantined: list[dict[str, Any]]


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"forward evidence input is unreadable: path={path}, error={error}") from error
    if not isinstance(value, dict):
        raise TypeError(f"forward evidence input must be an object: path={path}")
    return value


def _policy_replay_by_position(policy_replay: dict[str, Any]) -> dict[str, PolicyReplay]:
    raw_rows = policy_replay.get("trade_rows", [])
    if not isinstance(raw_rows, list):
        raise TypeError("forward policy replay trade_rows must be an array")
    rows: dict[str, PolicyReplay] = {}
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, dict):
            raise TypeError(f"forward policy replay row must be an object: index={index}")
        position_id = str(raw_row.get("position_id", ""))
        if not position_id:
            raise ValueError(f"forward policy replay row lacks position_id: index={index}")
        entry_reasons = raw_row.get("entry_policy_rejection_reasons", [])
        exit_reasons = raw_row.get("exit_policy_rejection_reasons", [])
        if not isinstance(entry_reasons, list) or not isinstance(exit_reasons, list):
            raise TypeError(f"forward policy replay rejection reasons must be arrays: position_id={position_id}")
        rows[position_id] = {
            "entry_rejection_reasons": tuple(str(reason) for reason in entry_reasons),
            "exit_rejection_reasons": tuple(str(reason) for reason in exit_reasons),
        }
    return rows


def _explicit_outcome_class(trade: dict[str, Any]) -> OutcomeClass | None:
    value = str(trade.get("outcome_integrity_class", trade.get("outcome_validity", "")))
    if value in {VALIDATED_OUTCOME, CENSORED_OUTCOME, QUARANTINED_OUTCOME}:
        return value  # type: ignore[return-value]
    return None


def classify_closed_trade(
    trade: dict[str, Any],
    policy_replay: PolicyReplay | None,
) -> tuple[OutcomeClass, tuple[str, ...]]:
    explicit = _explicit_outcome_class(trade)
    if explicit is not None:
        raw_reasons = trade.get("outcome_integrity_reason_codes", [])
        if not isinstance(raw_reasons, list):
            raise TypeError("outcome_integrity_reason_codes must be an array")
        return explicit, tuple(str(reason) for reason in raw_reasons)
    if str(trade.get("exit_reason", "")) == "stale_contract_forced_close_at_last_executable_bid":
        return CENSORED_OUTCOME, (
            "contract_quote_continuity_lost",
            "stale_quote_is_not_an_exit_observation",
        )
    if policy_replay is not None:
        reasons = (
            *policy_replay["entry_rejection_reasons"],
            *policy_replay["exit_rejection_reasons"],
        )
        if reasons:
            return QUARANTINED_OUTCOME, tuple(dict.fromkeys(reasons))
        return VALIDATED_OUTCOME, ("legacy_policy_replay_conforms_to_current_entry_and_exit_policy",)
    if (
        trade.get("entry_policy_version") == ENTRY_POLICY_VERSION
        and trade.get("exit_policy_version") == EXIT_POLICY_VERSION
        and trade.get("exit_quote_quality_status") == "executable_quote"
    ):
        return VALIDATED_OUTCOME, ("current_entry_and_exit_policy_versions_verified",)
    return QUARANTINED_OUTCOME, ("legacy_outcome_lacks_complete_current_policy_proof",)


def classify_outcomes(
    ledger: dict[str, Any],
    policy_replay_artifact: dict[str, Any] | None,
) -> ClassifiedOutcomes:
    raw_closed = ledger.get("closed_trades", [])
    if not isinstance(raw_closed, list):
        raise TypeError("forward ledger closed_trades must be an array")
    policy_rows = _policy_replay_by_position(policy_replay_artifact or {})
    classified: ClassifiedOutcomes = {"validated": [], "censored": [], "quarantined": []}
    target_by_class: dict[OutcomeClass, str] = {
        VALIDATED_OUTCOME: "validated",
        CENSORED_OUTCOME: "censored",
        QUARANTINED_OUTCOME: "quarantined",
    }
    for index, raw_trade in enumerate(raw_closed):
        if not isinstance(raw_trade, dict):
            raise TypeError(f"forward ledger closed trade must be an object: index={index}")
        position_id = str(raw_trade.get("position_id", ""))
        if not position_id:
            raise ValueError(f"forward ledger closed trade lacks position_id: index={index}")
        outcome_class, reasons = classify_closed_trade(raw_trade, policy_rows.get(position_id))
        record = {
            **raw_trade,
            "outcome_integrity_version": INTEGRITY_VERSION,
            "outcome_integrity_class": outcome_class,
            "outcome_integrity_reason_codes": list(reasons),
            "included_in_forward_performance_statistics": outcome_class == VALIDATED_OUTCOME,
            "historical_record_preserved": True,
        }
        classified[target_by_class[outcome_class]].append(record)
    raw_censored = ledger.get("censored_positions", [])
    if not isinstance(raw_censored, list):
        raise TypeError("forward ledger censored_positions must be an array")
    for index, raw_position in enumerate(raw_censored):
        if not isinstance(raw_position, dict):
            raise TypeError(f"forward ledger censored position must be an object: index={index}")
        position_id = str(raw_position.get("position_id", ""))
        if not position_id:
            raise ValueError(f"forward ledger censored position lacks position_id: index={index}")
        raw_reasons = raw_position.get(
            "outcome_integrity_reason_codes",
            ["contract_quote_continuity_lost", "no_exit_fill_observed"],
        )
        if not isinstance(raw_reasons, list):
            raise TypeError(
                f"censored outcome_integrity_reason_codes must be an array: position_id={position_id}"
            )
        classified["censored"].append(
            {
                **raw_position,
                "outcome_integrity_version": INTEGRITY_VERSION,
                "outcome_integrity_class": CENSORED_OUTCOME,
                "outcome_integrity_reason_codes": list(raw_reasons),
                "included_in_forward_performance_statistics": False,
                "historical_record_preserved": True,
            }
        )
    return classified


def validated_closed_trades(
    ledger: dict[str, Any],
    policy_replay_artifact: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    return classify_outcomes(ledger, policy_replay_artifact)["validated"]


def build_integrity_summary(
    ledger: dict[str, Any],
    policy_replay_artifact: dict[str, Any] | None,
) -> tuple[dict[str, Any], ClassifiedOutcomes]:
    outcomes = classify_outcomes(ledger, policy_replay_artifact)
    validated = outcomes["validated"]
    validated_pnls = [float(trade["path_pnl"]) for trade in validated]
    entry_cohorts = sorted({str(trade.get("entry_date", "")) for trade in validated if trade.get("entry_date")})
    signal_families = sorted({str(trade.get("signal_family", "")) for trade in validated if trade.get("signal_family")})
    summary = {
        "artifact_type": "forward_evidence_integrity_summary",
        "integrity_version": INTEGRITY_VERSION,
        "integrity_status": "forward_outcomes_classified_fail_closed",
        "raw_closed_record_count": sum(len(records) for records in outcomes.values()),
        "validated_closed_trade_count": len(validated),
        "validated_win_count": sum(pnl > 0 for pnl in validated_pnls),
        "validated_loss_count": sum(pnl < 0 for pnl in validated_pnls),
        "validated_net_pnl_premium_units": round(sum(validated_pnls), 6),
        "validated_entry_cohort_count": len(entry_cohorts),
        "validated_entry_cohorts": entry_cohorts,
        "validated_signal_family_count": len(signal_families),
        "validated_signal_families": signal_families,
        "censored_outcome_count": len(outcomes["censored"]),
        "quarantined_outcome_count": len(outcomes["quarantined"]),
        "statistics_exclude_censored_and_quarantined_outcomes": True,
        "raw_history_rewritten": False,
        "not_profitability_claim": True,
        "paper_only": True,
        "live_blocked": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    return summary, outcomes


def run_forward_evidence_integrity() -> dict[str, Any]:
    ledger = _load_json(LEDGER_PATH)
    policy_replay = _load_json(POLICY_REPLAY_PATH) if POLICY_REPLAY_PATH.exists() else {}
    summary, outcomes = build_integrity_summary(ledger, policy_replay)
    write_integrity_artifacts(summary, outcomes)
    return summary


def write_integrity_artifacts(
    summary: dict[str, Any],
    outcomes: ClassifiedOutcomes,
) -> None:
    write_json_atomic(INTEGRITY_SUMMARY_PATH, summary)
    write_jsonl_atomic(VALIDATED_OUTCOMES_PATH, outcomes["validated"])
    write_jsonl_atomic(CENSORED_OUTCOMES_PATH, outcomes["censored"])
    write_jsonl_atomic(QUARANTINED_OUTCOMES_PATH, outcomes["quarantined"])


if __name__ == "__main__":
    print(json.dumps(run_forward_evidence_integrity(), indent=2, sort_keys=True))
