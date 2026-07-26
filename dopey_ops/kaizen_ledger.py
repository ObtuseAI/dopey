"""Kaizen Defect Ledger: one queue for every defect the system already records.

Toyota's jidoka principle: any worker can stop the line, and every stoppage
becomes a visible, countable defect that kaizen works down. DOPEY already
"pulls the andon cord" in half a dozen places - stress repair items, censored
positions, failed supervisor stages, provider disagreements, unreliable-quote
deferrals - but each lands in its own artifact and nothing aggregates them,
so recurring defects hide in plain sight. This ledger sweeps every known
defect source into ONE prioritized queue: defect type, source, count, and the
newest example, ordered by frequency.

Measure-only: the ledger recommends attention, never repairs anything itself.
A defect class disappearing from the queue because its source artifact went
missing is itself surfaced as a defect (missing_defect_source).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_research_pipeline.artifact_io import write_json_atomic

REPO_ROOT = Path(__file__).resolve().parent.parent
ART = REPO_ROOT / "artifacts" / "dopey"
KAIZEN_PATH = ART / "ops" / "kaizen_ledger.json"

KAIZEN_VERSION = "dopey-kaizen-ledger-v1"
TOP_DEFECTS = 15


def _load_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    rows.append(parsed)
    except (OSError, json.JSONDecodeError):
        return []
    return rows


def _defect(source: str, defect_type: str, count: int, example: str) -> dict[str, Any]:
    return {
        "source": source,
        "defect_type": defect_type,
        "count": count,
        "latest_example": example[:240],
    }


def collect_defects() -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = []

    # 1. Adversarial stress repair items (book vulnerabilities).
    repairs = _load_jsonl(
        ART / "adversarial_stress" / "adversarial_stress_repair_items.jsonl"
    )
    by_reason: dict[str, list[dict[str, Any]]] = {}
    for item in repairs:
        by_reason.setdefault(str(item.get("reason", "unknown")), []).append(item)
    for reason, items in by_reason.items():
        defects.append(
            _defect(
                "adversarial_stress",
                reason,
                len(items),
                str(items[-1].get("detail", "")),
            )
        )

    # 2. Censored forward positions (quote-continuity failures = lost evidence).
    ledger = _load_json(ART / "forward_walk" / "forward_walk_ledger.json")
    censored = ledger.get("censored_positions", [])
    if isinstance(censored, list) and censored:
        reasons: dict[str, int] = {}
        for position in censored:
            for code in position.get("censor_reason_codes", ["uncoded_censor"]):
                reasons[str(code)] = reasons.get(str(code), 0) + 1
        for code, count in reasons.items():
            defects.append(
                _defect(
                    "forward_walk_censoring", code, count, f"{count} positions censored"
                )
            )

    # 3. Unreliable-quote deferrals on the open book (throughput leak).
    deferred = [
        p
        for p in ledger.get("open_positions", [])
        if str(p.get("last_quote_quality_status", "")) == "deferred_unreliable_quote"
    ]
    if deferred:
        defects.append(
            _defect(
                "forward_walk_marking",
                "deferred_unreliable_quote",
                len(deferred),
                ", ".join(sorted(str(p.get("symbol", "")) for p in deferred)[:8]),
            )
        )

    # 4. Supervisor stage failures from the newest journal entry.
    journal = _load_jsonl(ART / "research_supervisor" / "supervisor_run_journal.jsonl")
    if journal:
        newest = journal[-1]
        stage_states = newest.get("stage_states", {})
        failed = sorted(
            name
            for name, state in stage_states.items()
            if isinstance(state, str) and state.startswith("failed")
        )
        if failed:
            defects.append(
                _defect(
                    "research_supervisor",
                    "failed_stages_latest_run",
                    len(failed),
                    ", ".join(failed),
                )
            )
    else:
        defects.append(
            _defect(
                "research_supervisor",
                "missing_defect_source",
                1,
                "no supervisor journal found",
            )
        )

    # 5. Cross-provider disagreements (data integrity).
    provider = _load_json(ART / "cross_provider" / "cross_provider_check.json")
    disagreements = provider.get("disagreement_count")
    if isinstance(disagreements, int) and disagreements > 0:
        defects.append(
            _defect(
                "cross_provider_check",
                "provider_disagreement",
                disagreements,
                str(provider.get("headline", "")),
            )
        )

    # 6. Phantom censoring in the veto shadow lane (lost measurement).
    shadow = _load_json(ART / "forward_walk" / "veto_shadow_summary.json")
    shadow_censored = shadow.get("censored_phantom_count")
    if isinstance(shadow_censored, int) and shadow_censored > 0:
        defects.append(
            _defect(
                "veto_shadow",
                "censored_phantoms",
                shadow_censored,
                f"{shadow_censored} phantoms lost quote continuity",
            )
        )

    # 7. Provider-fetch failures that survived retries (chain + earnings lanes).
    manifest = _load_json(
        REPO_ROOT / "dopey_data" / "real" / "manifests" / "options_data_manifest.json"
    )
    chain_failed = manifest.get("fetch_health", {}).get(
        "symbols_failed_after_retries", {}
    )
    if isinstance(chain_failed, dict) and chain_failed:
        defects.append(
            _defect(
                "chain_fetch",
                "symbol_fetch_failed_after_retries",
                len(chain_failed),
                ", ".join(sorted(chain_failed)[:8]),
            )
        )
    earnings_dir = REPO_ROOT / "dopey_data" / "real" / "raw" / "earnings_calendar"
    health_files = (
        sorted(earnings_dir.glob("*_earnings_fetch_health.json"))
        if earnings_dir.exists()
        else []
    )
    if health_files:
        earnings_health = _load_json(health_files[-1])
        earnings_failed = earnings_health.get("symbols_failed_after_retries", {})
        if isinstance(earnings_failed, dict) and earnings_failed:
            defects.append(
                _defect(
                    "earnings_fetch",
                    "symbol_fetch_failed_after_retries",
                    len(earnings_failed),
                    ", ".join(sorted(earnings_failed)[:8]),
                )
            )

    return sorted(defects, key=lambda d: -int(d["count"]))


def run_kaizen_ledger() -> dict[str, Any]:
    defects = collect_defects()
    summary = {
        "artifact_type": "kaizen_ledger",
        "kaizen_version": KAIZEN_VERSION,
        "kaizen_status": "kaizen_ledger_current",
        "defect_class_count": len(defects),
        "total_defect_count": sum(int(d["count"]) for d in defects),
        "top_defects": defects[:TOP_DEFECTS],
        "headline": (
            f"{len(defects)} defect classes, {sum(int(d['count']) for d in defects)} total; "
            + (
                f"worst: {defects[0]['defect_type']} ({defects[0]['count']})"
                if defects
                else "queue empty"
            )
        ),
        "coaching_principle": (
            "work the queue top-down; a defect class recurring across weeks is a system "
            "problem, not an incident"
        ),
        "never_a_gate_input": True,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    write_json_atomic(KAIZEN_PATH, summary)
    return summary
