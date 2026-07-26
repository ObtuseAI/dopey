"""Conservative synthesis of promotion eligibility from existing research ledgers."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from dopey.protocols.identity import canonical_hash


def _load_object(path: Path) -> dict[str, Any]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"promotion synthesis input must be an object: path={path}")
    return raw


def _load_jsonl(path: Path) -> tuple[dict[str, Any], ...]:
    if not path.exists():
        return ()
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        raw: Any = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError(f"promotion synthesis ledger record must be an object: path={path}, line={line_number}")
        records.append(raw)
    return tuple(records)


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def synthesize_promotion_evidence(
    autoresearch_cycle_path: Path,
    forward_prediction_ledger_path: Path,
    public_history_root: Path,
    output_path: Path,
    issued_at: datetime,
) -> dict[str, Any]:
    if issued_at.tzinfo is None:
        raise ValueError("promotion evidence synthesis issued_at must be timezone-aware")
    cycle = _load_object(autoresearch_cycle_path)
    raw_candidates = cycle.get("candidates", [])
    if not isinstance(raw_candidates, list) or any(not isinstance(record, dict) for record in raw_candidates):
        raise ValueError(f"autoresearch candidates must be an object array: path={autoresearch_cycle_path}")
    predictions = _load_jsonl(forward_prediction_ledger_path)
    pending_by_symbol: Counter[str] = Counter()
    settled_by_symbol: Counter[str] = Counter()
    for prediction in predictions:
        symbol = str(prediction.get("symbol", "")).strip()
        if not symbol:
            raise ValueError(
                f"forward prediction lacks a symbol: path={forward_prediction_ledger_path}, "
                f"prediction_id={prediction.get('prediction_id')}"
            )
        if prediction.get("prediction_status") == "pending_forward_settlement":
            pending_by_symbol[symbol] += 1
        elif prediction.get("prediction_status") == "settled_forward_outcome":
            settled_by_symbol[symbol] += 1
    unresolved_symbols: list[dict[str, Any]] = []
    for symbol in sorted(set(pending_by_symbol) | set(settled_by_symbol)):
        history_path = public_history_root / f"{symbol}.csv"
        history_rows = max(0, len(history_path.read_text(encoding="utf-8").splitlines()) - 1) if history_path.exists() else 0
        unresolved_symbols.append(
            {
                "symbol_id": symbol,
                "history_rows": history_rows,
                "pending_forward_samples": pending_by_symbol[symbol],
                "settled_forward_samples": settled_by_symbol[symbol],
                "missing_evidence": [
                    "deterministic_symbol_replay",
                    "private_selection_samples",
                    "external_generalization_samples",
                    "minimum_forward_samples",
                    "independent_strategy_contribution",
                    "causal_and_calibration_statistics",
                ],
                "eligible_for_protected_gate": False,
            }
        )
    unresolved_strategies = [
        {
            "strategy_id": str(candidate.get("strategy_id", "unknown")),
            "lineage_id": str(candidate.get("lineage_id", "unknown")),
            "generation": int(candidate.get("generation", 0) or 0),
            "missing_evidence": [
                "deterministic_backtest_samples",
                "private_selection_samples",
                "external_generalization_samples",
                "forward_settlements",
                "cross_symbol_era_regime_transfer",
                "causal_calibration_and_complexity_statistics",
            ],
            "eligible_for_protected_gate": False,
        }
        for candidate in raw_candidates
    ]
    source_hashes = {
        "autoresearch_cycle": canonical_hash(cycle),
        "forward_prediction_ledger": canonical_hash(predictions),
        "public_history_index": canonical_hash(
            {record["symbol_id"]: record["history_rows"] for record in unresolved_symbols}
        ),
    }
    body: dict[str, Any] = {
        "artifact_type": "autonomous_promotion_evidence_synthesis",
        "synthesis_version": "dopey-promotion-evidence-synthesis-v2",
        "synthesis_status": "complete",
        "eligibility_status": "no_eligible_records",
        "issued_at": issued_at.isoformat(),
        "source_hashes": source_hashes,
        "symbols": [],
        "strategies": [],
        "pairs": [],
        "strategy_blueprints": list(raw_candidates),
        "unresolved_symbols": unresolved_symbols,
        "unresolved_strategies": unresolved_strategies,
        "unresolved_pair_reason": "no settled symbol-to-strategy attribution exists",
        "eligible_symbol_count": 0,
        "eligible_strategy_count": 0,
        "eligible_pair_count": 0,
        "candidate_self_evaluation_allowed": False,
        "missing_evidence_fabricated": False,
        "backtest_counted_as_forward": False,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    output = {**body, "synthesis_hash": canonical_hash(body)}
    _write_json_atomic(output_path, output)
    return output
