"""Materialize leveraged ETF swing plans from current validated chart evidence."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from dopey_data.history_validator import validate_default_history_dataset

from .leveraged_etf import (
    build_leveraged_etf_swing_plans,
    preferred_leveraged_etf_plans,
)
from .market_structure import group_history_bars


REPO_ROOT = Path(__file__).resolve().parent.parent
THESIS_PATH = (
    REPO_ROOT / "artifacts" / "dopey" / "equity_swing" / "equity_swing_theses.jsonl"
)
PLAN_PATH = (
    REPO_ROOT
    / "artifacts"
    / "dopey"
    / "equity_swing"
    / "leveraged_etf_swing_plans.jsonl"
)
SUMMARY_PATH = (
    REPO_ROOT
    / "artifacts"
    / "dopey"
    / "equity_swing"
    / "leveraged_etf_swing_plan_summary.json"
)


def run_leveraged_etf_swing_planner() -> dict[str, Any]:
    history_result = validate_default_history_dataset()
    if history_result.get("dataset_status") != "valid_real_dataset":
        raise ValueError(
            "leveraged ETF planner requires valid real history: "
            f"dataset_status={history_result.get('dataset_status')}"
        )
    theses = _read_jsonl(THESIS_PATH)
    histories = group_history_bars(list(history_result["bars_loaded"]))
    plans = build_leveraged_etf_swing_plans(theses, histories)
    _write_jsonl_atomic(PLAN_PATH, plans)
    actionable = [
        plan
        for plan in plans
        if plan.get("plan_status") == "actionable_shadow_leveraged_etf_plan"
    ]
    preferred_actionable = preferred_leveraged_etf_plans(actionable)
    summary = {
        "artifact_type": "leveraged_etf_swing_plan_summary",
        "schema_version": "dopey-leveraged-etf-swing-plan-summary-v2",
        "run_status": "leveraged_etf_plans_materialized",
        "supported_pair_count": len({str(plan["pair_id"]) for plan in plans}),
        "supported_product_count": len(plans),
        "actionable_plan_count": len(actionable),
        "actionable_trade_symbols": [str(plan["trade_symbol"]) for plan in actionable],
        "preferred_actionable_plan_count": len(preferred_actionable),
        "preferred_actionable_trade_symbols": [
            str(plan["trade_symbol"]) for plan in preferred_actionable
        ],
        "analysis_symbols": sorted({str(plan["analysis_symbol"]) for plan in plans}),
        "product_categories": sorted({str(plan["product_category"]) for plan in plans}),
        "chart_authority_policy": "underlying_or_declared_benchmark_proxy_only",
        "bearish_construction": "long_inverse_etf_shares_no_direct_short_sale",
        "paper_twin_required": True,
        "plan_path": str(PLAN_PATH),
    }
    _write_json_atomic(SUMMARY_PATH, summary)
    return summary


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"leveraged ETF source thesis ledger is missing: path={path}"
        )
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not raw.strip():
            continue
        try:
            record = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"invalid leveraged ETF source thesis JSON: path={path}, line={line_number}, error={error}"
            ) from error
        if not isinstance(record, dict):
            raise TypeError(
                f"leveraged ETF source thesis must be an object: path={path}, line={line_number}"
            )
        records.append(record)
    return records


def _write_jsonl_atomic(path: Path, records: list[dict[str, Any]]) -> None:
    payload = "".join(
        json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
        for record in records
    )
    _write_text_atomic(path, payload)


def _write_json_atomic(path: Path, record: dict[str, Any]) -> None:
    _write_text_atomic(
        path, json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n"
    )


def _write_text_atomic(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


if __name__ == "__main__":
    print(json.dumps(run_leveraged_etf_swing_planner(), sort_keys=True))
