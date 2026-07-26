"""Build the source-backed DOPEY paper-trade readiness frontier."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from dopey.ascendancy.readiness_frontier import build_trade_readiness_frontier


SOURCE_PATHS: tuple[tuple[str, Path], ...] = (
    ("action_gate", Path("artifacts/dopey/broker_readiness/action_readiness_gate.json")),
    ("nightly", Path("artifacts/dopey/nightly/nightly_latest.json")),
    ("options_contract", Path("artifacts/dopey/options_data_contract/options_data_contract_summary.json")),
    ("history_manifest", Path("dopey_data/history/history_dataset_manifest.json")),
    ("stress_summary", Path("artifacts/dopey/portfolio_stress_ladder/stress_ladder_summary.json")),
    ("incident_summary", Path("artifacts/dopey/incident_response/incident_rehearsal_summary.json")),
    ("lifecycle_summary", Path("artifacts/dopey/lifecycle/lifecycle_summary.json")),
)


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"trade readiness source artifact is missing: path={path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise TypeError(f"trade readiness source must be a JSON object: path={path}")
    return cast(dict[str, object], value)


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def _render_report(frontier: dict[str, object]) -> str:
    levels_value = frontier.get("levels")
    levels = levels_value if isinstance(levels_value, dict) else {}
    blocked_value = frontier.get("blocked_gates")
    blocked = blocked_value if isinstance(blocked_value, list) else []
    actions_value = frontier.get("autonomous_next_action_queue")
    actions = actions_value if isinstance(actions_value, list) else []
    lines = [
        "# DOPEY Trade Readiness Frontier",
        "",
        f"- status: `{frontier.get('frontier_status', 'unknown')}`",
        f"- highest operational level: `{frontier.get('highest_operational_level', 'unknown')}`",
        "- authority: `paper-only; live execution constitutionally unavailable`",
        f"- reproducibility hash: `{frontier.get('reproducibility_hash', '')}`",
        "",
        "## Capability levels",
        "",
        "| Level | Ready | Meaning |",
        "|---|---:|---|",
    ]
    meanings = {
        "research_mechanics": "Governed data plus deterministic risk, incident, and lifecycle mechanics.",
        "stock_shadow": "Stocks may produce forward paper decisions after current validation is green.",
        "option_shadow": "Options additionally require observed, validated, quote-priced chain evidence.",
        "strategy_promotion": "Forward sample, net evidence, regime robustness, and statistical truth all pass.",
        "live_execution": "Permanently outside this repository's authority.",
    }
    for level_id in meanings:
        level = levels.get(level_id)
        ready = level.get("ready") if isinstance(level, dict) else None
        lines.append(f"| `{level_id}` | `{ready}` | {meanings[level_id]} |")
    lines.extend(["", "## Blocking gates", ""])
    if not blocked:
        lines.append("- None reported.")
    for item in blocked:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"- `{item.get('gate_id', 'unknown')}` — {item.get('detail', 'no detail')} "
            f"(evidence: `{item.get('evidence_class', 'unknown')}`)"
        )
    lines.extend(["", "## Autonomous next-action queue", ""])
    if not actions:
        lines.append("- No action is justified by the current frontier.")
    for index, action in enumerate(actions, start=1):
        lines.append(f"{index}. {action}")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "Mechanics readiness, paper-shadow readiness, strategy evidence, and live authority are separate.",
            "A green lower tier never implies a green higher tier. Simulation never becomes realized evidence.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_trade_readiness_frontier(
    repository_root: Path,
    output_path: Path,
    report_path: Path,
) -> dict[str, object]:
    resolved_root = repository_root.resolve()
    sources = {
        source_id: _read_json_object(resolved_root / relative_path)
        for source_id, relative_path in SOURCE_PATHS
    }
    frontier = build_trade_readiness_frontier(
        sources["action_gate"],
        sources["nightly"],
        sources["options_contract"],
        sources["history_manifest"],
        sources["stress_summary"],
        sources["incident_summary"],
        sources["lifecycle_summary"],
    )
    _write_text_atomic(
        output_path,
        json.dumps(frontier, indent=2, sort_keys=True) + "\n",
    )
    _write_text_atomic(report_path, _render_report(frontier))
    return {
        **frontier,
        "artifact_paths": {
            "trade_readiness_frontier": str(output_path),
            "trade_readiness_report": str(report_path),
        },
    }


def main() -> int:
    repository_root = Path(__file__).resolve().parents[2]
    run_trade_readiness_frontier(
        repository_root,
        repository_root / "artifacts" / "dopey" / "readiness" / "trade_readiness_frontier.json",
        repository_root / "docs" / "reports" / "DOPEY_TRADE_READINESS_FRONTIER_REPORT.md",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
