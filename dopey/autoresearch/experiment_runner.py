"""Deterministic, independent evaluation for executable autoresearch lineages."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Final, TypedDict

from dopey.protocols.identity import canonical_hash

from .schema import ResearchFinding


SUPPORTED_LINEAGE_GENES: dict[str, frozenset[str]] = {
    "technical_momentum": frozenset(
        {
            "weekly_trend",
            "daily_momentum",
            "volume_confirmation",
            "regime_abstention",
        }
    ),
    "structural_trend": frozenset(
        {
            "swing_structure",
            "break_acceptance",
            "relative_strength",
            "failure_exit",
        }
    ),
}
PREFERRED_SYMBOLS: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "JPM",
    "XLE",
    "XLF",
)
FORWARD_HORIZON = 5
ROUND_TRIP_COST_FRACTION = 0.001
MIN_EXTERNAL_SAMPLES = 30
EVALUATOR_VERSION: Final[str] = "dopey-autoresearch-experiment-evaluator-v2"
MUTATION_PREFIXES: Final[frozenset[str]] = frozenset(
    {
        "novelty_probe",
        "repair_failure",
        "retain_success",
        "challenge_backtest",
        "expand_evidence",
        "repair_calibration",
        "learn_forward_outcome",
    }
)


class Bar(TypedDict):
    date: str
    high: float
    close: float
    volume: float


class PartitionMetrics(TypedDict):
    sample_count: int
    mean_after_cost_return: float | None
    hit_rate: float | None


class CandidatePolicy(TypedDict):
    lineage_id: str
    trend_lookback: int
    trigger_lookback: int
    context_lookback: int
    volume_multiplier: float
    breakout_buffer_fraction: float
    mutation_gene: str


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def _append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _last_jsonl_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"autoresearch experiment ledger is missing: path={path}")
    latest: dict[str, Any] | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                decoded: Any = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(
                    "autoresearch experiment ledger contains invalid JSON: "
                    f"path={path}, line={line_number}, error={error}"
                ) from error
            if not isinstance(decoded, dict):
                raise ValueError(
                    "autoresearch experiment ledger row must be an object: "
                    f"path={path}, line={line_number}"
                )
            latest = decoded
    if latest is None:
        raise ValueError(f"autoresearch experiment ledger is empty: path={path}")
    claimed_hash = latest.get("cycle_hash")
    unhashed = dict(latest)
    unhashed.pop("cycle_hash", None)
    if not isinstance(claimed_hash, str) or canonical_hash(unhashed) != claimed_hash:
        raise ValueError(
            f"autoresearch experiment cycle hash validation failed: path={path}"
        )
    return latest


def _load_manifest(manifest_path: Path) -> dict[str, dict[str, Any]]:
    decoded: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError(f"history manifest must be an object: path={manifest_path}")
    raw_files = decoded.get("data_files")
    if not isinstance(raw_files, list):
        raise ValueError(
            f"history manifest data_files must be an array: path={manifest_path}"
        )
    records: dict[str, dict[str, Any]] = {}
    for index, raw_record in enumerate(raw_files):
        if not isinstance(raw_record, dict):
            raise ValueError(
                "history manifest data file must be an object: "
                f"path={manifest_path}, index={index}"
            )
        raw_symbols = raw_record.get("symbols")
        if (
            not isinstance(raw_symbols, list)
            or len(raw_symbols) != 1
            or not isinstance(raw_symbols[0], str)
        ):
            continue
        records[raw_symbols[0].upper()] = dict(raw_record)
    return records


def _load_pinned_bars(
    history_root: Path,
    manifest_record: dict[str, Any],
    symbol: str,
) -> tuple[tuple[Bar, ...], str]:
    relative_path = manifest_record.get("path")
    expected_hash = manifest_record.get("sha256")
    if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
        raise ValueError(
            f"history manifest pin is incomplete: symbol={symbol}, record={manifest_record}"
        )
    path = history_root / relative_path
    payload = path.read_bytes()
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_hash != expected_hash:
        raise ValueError(
            "history file failed manifest hash validation: "
            f"symbol={symbol}, path={path}, expected={expected_hash}, actual={actual_hash}"
        )
    bars: list[Bar] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            try:
                high = float(row["high"])
                close = float(row["close"])
                volume = float(row["volume"])
                row_date = str(row["date"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(
                    "history row is invalid for autoresearch evaluation: "
                    f"symbol={symbol}, path={path}, row={row_number}, error={error}"
                ) from error
            if (
                not row_date
                or not math.isfinite(high)
                or not math.isfinite(close)
                or not math.isfinite(volume)
                or high <= 0.0
                or close <= 0.0
                or volume < 0.0
            ):
                raise ValueError(
                    "history row has invalid market values for autoresearch evaluation: "
                    f"symbol={symbol}, path={path}, row={row_number}"
                )
            bars.append(
                {
                    "date": row_date,
                    "high": high,
                    "close": close,
                    "volume": volume,
                }
            )
    if len(bars) < 120:
        raise ValueError(
            f"history is too short for autoresearch evaluation: symbol={symbol}, rows={len(bars)}"
        )
    return tuple(bars), actual_hash


def _mean(values: tuple[float, ...]) -> float:
    return sum(values) / float(len(values))


def _partition(index: int, count: int) -> str:
    ratio = index / float(count)
    if ratio < 0.60:
        return "VISIBLE_DEVELOPMENT"
    if ratio < 0.80:
        return "PRIVATE_SELECTION"
    return "EXTERNAL_GENERALIZATION"


def _technical_signal(
    bars: tuple[Bar, ...],
    index: int,
    spy_regime_by_date: dict[str, bool],
    policy: CandidatePolicy,
) -> bool:
    close = bars[index]["close"]
    trend_lookback = policy["trend_lookback"]
    trigger_lookback = policy["trigger_lookback"]
    average_close = _mean(
        tuple(bar["close"] for bar in bars[index - trend_lookback : index])
    )
    average_volume = _mean(
        tuple(bar["volume"] for bar in bars[index - trend_lookback : index])
    )
    return (
        close > average_close
        and close > bars[index - trigger_lookback]["close"]
        and bars[index]["volume"]
        > average_volume * policy["volume_multiplier"]
        and spy_regime_by_date.get(bars[index]["date"]) is True
    )


def _structural_signal(
    bars: tuple[Bar, ...],
    index: int,
    spy_return_by_date: dict[str, float],
    policy: CandidatePolicy,
) -> bool:
    trigger_lookback = policy["trigger_lookback"]
    context_lookback = policy["context_lookback"]
    prior_high = max(
        bar["high"] for bar in bars[index - trigger_lookback : index]
    )
    symbol_return = (
        bars[index]["close"] / bars[index - context_lookback]["close"] - 1.0
    )
    spy_return = spy_return_by_date.get(bars[index]["date"])
    return (
        spy_return is not None
        and bars[index]["close"]
        > prior_high * (1.0 + policy["breakout_buffer_fraction"])
        and symbol_return > spy_return
    )


def _market_context(
    spy_bars: tuple[Bar, ...],
) -> tuple[dict[str, bool], dict[str, float]]:
    regime: dict[str, bool] = {}
    returns: dict[str, float] = {}
    for index in range(50, len(spy_bars)):
        row_date = spy_bars[index]["date"]
        average_close = _mean(
            tuple(bar["close"] for bar in spy_bars[index - 50 : index])
        )
        regime[row_date] = spy_bars[index]["close"] > average_close
        returns[row_date] = (
            spy_bars[index]["close"] / spy_bars[index - 20]["close"] - 1.0
        )
    return regime, returns


def _mutation_variant(mutation_gene: str) -> int:
    marker = mutation_gene.rsplit(":", maxsplit=1)[-1]
    if marker.startswith("variant") and marker[7:].isdigit():
        return int(marker[7:])
    if marker.startswith("slot") and marker[4:].isdigit():
        return int(marker[4:])
    return 0


def _candidate_policy(candidate: dict[str, Any]) -> CandidatePolicy:
    lineage_id = str(candidate.get("lineage_id", ""))
    raw_genes = candidate.get("genes")
    if not isinstance(raw_genes, (list, tuple)):
        raise ValueError(
            f"autoresearch candidate genes must be an array: lineage_id={lineage_id}"
        )
    mutation_genes = tuple(
        str(gene)
        for gene in raw_genes
        if str(gene).split(":", maxsplit=1)[0] in MUTATION_PREFIXES
    )
    if len(mutation_genes) != 1:
        raise ValueError(
            "compiled autoresearch candidate requires exactly one executable "
            f"mutation gene: strategy_id={candidate.get('strategy_id')}, "
            f"mutation_genes={mutation_genes}"
        )
    mutation_gene = mutation_genes[0]
    variant = _mutation_variant(mutation_gene) % 4
    if lineage_id == "technical_momentum":
        policies: tuple[CandidatePolicy, ...] = (
            {
                "lineage_id": lineage_id,
                "trend_lookback": 15,
                "trigger_lookback": 5,
                "context_lookback": 20,
                "volume_multiplier": 1.0,
                "breakout_buffer_fraction": 0.0,
                "mutation_gene": mutation_gene,
            },
            {
                "lineage_id": lineage_id,
                "trend_lookback": 20,
                "trigger_lookback": 10,
                "context_lookback": 20,
                "volume_multiplier": 1.0,
                "breakout_buffer_fraction": 0.0,
                "mutation_gene": mutation_gene,
            },
            {
                "lineage_id": lineage_id,
                "trend_lookback": 20,
                "trigger_lookback": 5,
                "context_lookback": 20,
                "volume_multiplier": 1.1,
                "breakout_buffer_fraction": 0.0,
                "mutation_gene": mutation_gene,
            },
            {
                "lineage_id": lineage_id,
                "trend_lookback": 30,
                "trigger_lookback": 5,
                "context_lookback": 20,
                "volume_multiplier": 1.0,
                "breakout_buffer_fraction": 0.0,
                "mutation_gene": mutation_gene,
            },
        )
        return policies[variant]
    if lineage_id == "structural_trend":
        policies = (
            {
                "lineage_id": lineage_id,
                "trend_lookback": 20,
                "trigger_lookback": 15,
                "context_lookback": 20,
                "volume_multiplier": 1.0,
                "breakout_buffer_fraction": 0.0,
                "mutation_gene": mutation_gene,
            },
            {
                "lineage_id": lineage_id,
                "trend_lookback": 20,
                "trigger_lookback": 30,
                "context_lookback": 20,
                "volume_multiplier": 1.0,
                "breakout_buffer_fraction": 0.0,
                "mutation_gene": mutation_gene,
            },
            {
                "lineage_id": lineage_id,
                "trend_lookback": 20,
                "trigger_lookback": 20,
                "context_lookback": 20,
                "volume_multiplier": 1.0,
                "breakout_buffer_fraction": 0.0025,
                "mutation_gene": mutation_gene,
            },
            {
                "lineage_id": lineage_id,
                "trend_lookback": 20,
                "trigger_lookback": 20,
                "context_lookback": 10,
                "volume_multiplier": 1.0,
                "breakout_buffer_fraction": 0.0,
                "mutation_gene": mutation_gene,
            },
        )
        return policies[variant]
    raise ValueError(
        f"autoresearch candidate lineage has no executable policy: lineage_id={lineage_id}"
    )


def _evaluate_candidate(
    candidate: dict[str, Any],
    bars_by_symbol: dict[str, tuple[Bar, ...]],
) -> dict[str, PartitionMetrics]:
    policy = _candidate_policy(candidate)
    lineage_id = policy["lineage_id"]
    spy_regime, spy_returns = _market_context(bars_by_symbol["SPY"])
    returns_by_partition: dict[str, list[float]] = {
        "VISIBLE_DEVELOPMENT": [],
        "PRIVATE_SELECTION": [],
        "EXTERNAL_GENERALIZATION": [],
    }
    for symbol in sorted(bars_by_symbol):
        bars = bars_by_symbol[symbol]
        for index in range(50, len(bars) - FORWARD_HORIZON):
            signal = (
                _technical_signal(bars, index, spy_regime, policy)
                if lineage_id == "technical_momentum"
                else _structural_signal(bars, index, spy_returns, policy)
            )
            if not signal:
                continue
            after_cost_return = (
                bars[index + FORWARD_HORIZON]["close"] / bars[index]["close"]
                - 1.0
                - ROUND_TRIP_COST_FRACTION
            )
            returns_by_partition[_partition(index, len(bars))].append(
                after_cost_return
            )
    output: dict[str, PartitionMetrics] = {}
    for partition, raw_returns in returns_by_partition.items():
        values = tuple(raw_returns)
        output[partition] = {
            "sample_count": len(values),
            "mean_after_cost_return": (
                round(_mean(values), 8) if values else None
            ),
            "hit_rate": (
                round(
                    sum(value > 0.0 for value in values) / float(len(values)),
                    8,
                )
                if values
                else None
            ),
        }
    return output


def _selection_key(
    candidate: dict[str, Any],
    metrics: dict[str, PartitionMetrics],
) -> tuple[float, float, int, str]:
    private = metrics["PRIVATE_SELECTION"]
    hit_rate = private["hit_rate"]
    mean_return = private["mean_after_cost_return"]
    return (
        hit_rate if hit_rate is not None else float("-inf"),
        mean_return if mean_return is not None else float("-inf"),
        private["sample_count"],
        str(candidate["strategy_id"]),
    )


def _compiled_candidates(cycle: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    raw_candidates = cycle.get("candidates")
    if not isinstance(raw_candidates, list):
        raise ValueError("autoresearch cycle candidates must be an array")
    compiled: dict[str, list[dict[str, Any]]] = {}
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            raise ValueError("autoresearch candidate must be an object")
        lineage_id = str(raw_candidate.get("lineage_id", ""))
        required_genes = SUPPORTED_LINEAGE_GENES.get(lineage_id)
        if required_genes is None:
            continue
        raw_genes = raw_candidate.get("genes")
        if not isinstance(raw_genes, (list, tuple)):
            raise ValueError(
                f"autoresearch candidate genes must be an array: lineage_id={lineage_id}"
            )
        gene_values = tuple(str(gene) for gene in raw_genes)
        semantic_genes = frozenset(
            gene
            for gene in gene_values
            if gene.split(":", maxsplit=1)[0] not in MUTATION_PREFIXES
        )
        mutation_genes = tuple(
            gene
            for gene in gene_values
            if gene.split(":", maxsplit=1)[0] in MUTATION_PREFIXES
        )
        if semantic_genes != required_genes or len(mutation_genes) != 1:
            continue
        compiled.setdefault(lineage_id, []).append(dict(raw_candidate))
    return compiled


def _evaluation_semantic_hash(record: dict[str, Any]) -> str:
    unhashed = dict(record)
    for field in (
        "evaluation_hash",
        "last_verified_at",
        "verification_hash",
        "verification_status",
    ):
        unhashed.pop(field, None)
    return canonical_hash(unhashed)


def _verification_fields(
    evaluation_hash: str,
    source_cycle_hash: str,
    history_hashes: dict[str, str],
    verified_at: datetime,
    verification_status: str,
) -> dict[str, str]:
    last_verified_at = verified_at.isoformat()
    return {
        "last_verified_at": last_verified_at,
        "verification_status": verification_status,
        "verification_hash": canonical_hash(
            {
                "evaluation_hash": evaluation_hash,
                "source_cycle_hash": source_cycle_hash,
                "history_hashes": history_hashes,
                "last_verified_at": last_verified_at,
                "verification_status": verification_status,
            }
        ),
    }


def _finding_from_evaluation(
    lineage_id: str,
    selected_candidate: dict[str, Any],
    metrics: dict[str, PartitionMetrics],
    evaluation_id: str,
) -> ResearchFinding | None:
    external = metrics["EXTERNAL_GENERALIZATION"]
    mean_return = external["mean_after_cost_return"]
    hit_rate = external["hit_rate"]
    if (
        external["sample_count"] < MIN_EXTERNAL_SAMPLES
        or mean_return is None
        or hit_rate is None
    ):
        return None
    successful = mean_return > 0.0 and hit_rate >= 0.52
    target_gene = (
        "volume_confirmation"
        if lineage_id == "technical_momentum"
        else "break_acceptance"
    )
    finding_type = "SUCCESS" if successful else "FAILURE"
    candidate_id = str(selected_candidate["strategy_id"])
    finding_body = {
        "finding_type": finding_type,
        "lineage_id": lineage_id,
        "target_gene": target_gene,
        "direction": (
            "retain_and_retest_on_new_forward_data"
            if successful
            else "tighten_or_replace"
        ),
        "evidence_id": f"{evaluation_id}:{candidate_id}",
    }
    return {
        "finding_id": "autoresearch-finding:"
        + canonical_hash(finding_body)[:24],
        **finding_body,
    }


def run_deterministic_experiment_evaluation(
    experiment_ledger_path: Path,
    history_manifest_path: Path,
    history_root: Path,
    findings_output_path: Path,
    evaluation_output_root: Path,
    issued_at: datetime,
) -> dict[str, Any]:
    if issued_at.tzinfo is None:
        raise ValueError("autoresearch experiment evaluation issued_at must be timezone-aware")
    cycle = _last_jsonl_object(experiment_ledger_path)
    cycle_hash = str(cycle["cycle_hash"])
    manifest = _load_manifest(history_manifest_path)
    selected_symbols = tuple(
        symbol for symbol in PREFERRED_SYMBOLS if symbol in manifest
    )
    if "SPY" not in selected_symbols or len(selected_symbols) < 4:
        raise ValueError(
            "autoresearch experiment evaluation needs SPY and at least three additional pinned symbols"
        )
    bars_by_symbol: dict[str, tuple[Bar, ...]] = {}
    history_hashes: dict[str, str] = {}
    for symbol in selected_symbols:
        bars, history_hash = _load_pinned_bars(
            history_root,
            manifest[symbol],
            symbol,
        )
        bars_by_symbol[symbol] = bars
        history_hashes[symbol] = history_hash
    latest_path = evaluation_output_root / "latest_experiment_evaluation.json"
    if latest_path.exists() and findings_output_path.exists():
        prior: Any = json.loads(latest_path.read_text(encoding="utf-8"))
        if (
            isinstance(prior, dict)
            and prior.get("source_cycle_hash") == cycle_hash
            and prior.get("history_hashes") == history_hashes
            and prior.get("evaluation_status") == "complete"
            and prior.get("evaluator_version") == EVALUATOR_VERSION
            and prior.get("evaluation_hash") == _evaluation_semantic_hash(prior)
        ):
            verification = _verification_fields(
                str(prior["evaluation_hash"]),
                cycle_hash,
                history_hashes,
                issued_at,
                "verified_source_and_history_unchanged",
            )
            refreshed = {**prior, **verification}
            _write_json_atomic(latest_path, refreshed)
            _append_jsonl(
                evaluation_output_root
                / "experiment_evaluation_verification_ledger.jsonl",
                {
                    "evaluation_id": refreshed["evaluation_id"],
                    "evaluation_hash": refreshed["evaluation_hash"],
                    "source_cycle_hash": cycle_hash,
                    "history_hashes": history_hashes,
                    **verification,
                    "paper_only": True,
                    "live_blocked": True,
                },
            )
            return refreshed
    compiled = _compiled_candidates(cycle)
    candidate_evaluations: list[dict[str, Any]] = []
    findings: list[ResearchFinding] = []
    evaluation_id = "autoresearch-evaluation:" + canonical_hash(
        {
            "source_cycle_hash": cycle_hash,
            "history_hashes": history_hashes,
            "evaluator_version": EVALUATOR_VERSION,
        }
    )[:24]
    for lineage_id in sorted(compiled):
        candidates = sorted(
            compiled[lineage_id],
            key=lambda candidate: str(candidate["strategy_id"]),
        )
        evaluated_candidates = tuple(
            (candidate, _evaluate_candidate(candidate, bars_by_symbol))
            for candidate in candidates
        )
        selected_candidate, selected_metrics = max(
            evaluated_candidates,
            key=lambda record: _selection_key(record[0], record[1]),
        )
        candidate_evaluations.append(
            {
                "lineage_id": lineage_id,
                "compiled_candidate_count": len(candidates),
                "selected_candidate_id": selected_candidate["strategy_id"],
                "selection_partition": "PRIVATE_SELECTION",
                "private_selection_item_feedback_exposed": False,
                "candidate_results": [
                    {
                        "strategy_id": candidate["strategy_id"],
                        "mutation_gene": _candidate_policy(candidate)[
                            "mutation_gene"
                        ],
                        "policy": _candidate_policy(candidate),
                        "metrics": metrics,
                        "selected": candidate["strategy_id"]
                        == selected_candidate["strategy_id"],
                    }
                    for candidate, metrics in evaluated_candidates
                ],
                "metrics": selected_metrics,
            }
        )
        finding = _finding_from_evaluation(
            lineage_id,
            selected_candidate,
            selected_metrics,
            evaluation_id,
        )
        if finding is not None:
            findings.append(finding)
    body: dict[str, Any] = {
        "artifact_type": "autoresearch_deterministic_experiment_evaluation",
        "evaluator_version": EVALUATOR_VERSION,
        "evaluation_status": "complete",
        "finding_status": (
            "complete_with_validated_findings"
            if findings
            else "complete_no_external_sample_qualified_findings"
        ),
        "issued_at": issued_at.isoformat(),
        "evaluation_id": evaluation_id,
        "source_cycle_hash": cycle_hash,
        "source_generation": cycle.get("generation"),
        "history_manifest_path": str(history_manifest_path),
        "history_hashes": history_hashes,
        "selected_symbols": list(selected_symbols),
        "compiled_lineage_count": len(compiled),
        "unsupported_lineage_count": len(
            {
                str(candidate.get("lineage_id", ""))
                for candidate in cycle.get("candidates", [])
                if isinstance(candidate, dict)
            }
            - set(compiled)
        ),
        "candidate_evaluations": candidate_evaluations,
        "finding_count": len(findings),
        "findings_output_path": str(findings_output_path),
        "candidate_self_grading_allowed": False,
        "private_selection_item_feedback_exposed": False,
        "external_generalization_required": True,
        "round_trip_cost_fraction": ROUND_TRIP_COST_FRACTION,
        "minimum_external_samples": MIN_EXTERNAL_SAMPLES,
        "automatic_research_activation_count": 0,
        "readiness_effect": "none",
        "execution_effect": "none",
        "paper_only": True,
        "live_blocked": True,
    }
    evaluation_hash = canonical_hash(body)
    verification = _verification_fields(
        evaluation_hash,
        cycle_hash,
        history_hashes,
        issued_at,
        "evaluated_current_source_and_history",
    )
    output = {
        **body,
        "evaluation_hash": evaluation_hash,
        **verification,
    }
    _write_json_atomic(findings_output_path, findings)
    _write_json_atomic(latest_path, output)
    _append_jsonl(
        evaluation_output_root / "experiment_evaluation_ledger.jsonl",
        output,
    )
    return output
