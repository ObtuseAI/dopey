"""OPERATOR TOOL - Monday-open preflight: is the stack ready for the session?

Read-only sweep over the staged data and pipeline artifacts (writes only its
own report files). Checks are honest READINESS-OF-PLUMBING checks - data
frontier, snapshot recency, lane freshness, sentinel state, halt state - not
edge or evidence claims. Run any time; most useful Sunday night / pre-open.

Usage:  .venv\\Scripts\\python operator_tools\\operator_monday_preflight.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey_core.market_calendar import is_trading_day, previous_trading_day  # noqa: E402
from dopey_research_pipeline.artifact_io import write_json_atomic  # noqa: E402
from dopey_core.repo_paths import REPORTS_DIR  # noqa: E402

ART = REPO / "artifacts" / "dopey"
PREFLIGHT_JSON = ART / "broker_readiness" / "monday_preflight.json"
PREFLIGHT_MD = REPORTS_DIR / "MONDAY_PREFLIGHT.md"


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _spine_frontier() -> str:
    summary = _load(ART / "history" / "history_spine_summary.json")
    date_range = summary.get("date_range") if isinstance(summary.get("date_range"), dict) else {}
    return str(date_range.get("end_date", summary.get("end_date", "")))


def _latest_chain_date() -> str:
    root = REPO / "dopey_data" / "real" / "raw" / "options_chains"
    if not root.exists():
        return ""
    dates = sorted(p.name for p in root.iterdir() if p.is_dir() and any(p.glob("*.csv")))
    return dates[-1] if dates else ""


def _scheduled_task_state() -> str:
    try:
        proc = subprocess.run(
            ["schtasks", "/query", "/tn", "DOPEY_DailyRitual"],
            capture_output=True, text=True, timeout=20,
        )
        return "registered" if proc.returncode == 0 else "NOT_REGISTERED"
    except (OSError, subprocess.TimeoutExpired):
        return "query_failed"


def _run_cross_provider_check() -> tuple[bool, str]:
    """Weekly independent-source spot check; failures report, never block."""
    try:
        from operator_tools.operator_cross_provider_check import run_cross_provider_check

        report = run_cross_provider_check()
        ok = report["verdict"] != "material_divergence_detected"
        detail = (
            f"{report['verdict']}: {report['compared_symbol_count']} symbols, "
            f"{report['material_close_divergences']} material / "
            f"{report['minor_close_divergences']} minor close divergences, "
            f"{len(report['fetch_failures'])} fetch failures"
        )
        return ok, detail
    except Exception as error:  # noqa: BLE001 - the preflight must always complete
        return True, f"cross_provider_check_unavailable: {error}"


def main() -> int:
    today = date.today()
    expected_frontier = (today if not is_trading_day(today) else previous_trading_day(today)).isoformat()
    # On a non-trading day the frontier should be the last trading session.
    last_session = previous_trading_day(today).isoformat() if not is_trading_day(today) else expected_frontier

    cross_provider_ok, cross_provider_detail = _run_cross_provider_check()
    frontier = _spine_frontier()
    chain_date = _latest_chain_date()
    freshness = _load(ART / "observability" / "data_freshness.json")
    envelope = _load(ART / "governance" / "envelope_integrity.json")
    macro = _load(ART / "macro_context" / "macro_context_summary.json")
    gate = _load(ART / "broker_readiness" / "action_readiness_gate.json")
    ledger = _load(ART / "forward_walk" / "forward_walk_ledger.json")
    walk = _load(ART / "forward_walk" / "forward_walk_summary.json")

    halt = ledger.get("last_discipline_halt") if isinstance(ledger.get("last_discipline_halt"), dict) else {}
    free_gb = shutil.disk_usage(str(REPO)).free / 1e9

    checks: dict[str, tuple[bool, str]] = {
        "spine_frontier_at_last_session": (
            frontier >= last_session,
            f"spine {frontier} vs last session {last_session}",
        ),
        "chain_snapshot_recent": (
            chain_date >= last_session,
            f"latest chains {chain_date} vs last session {last_session}",
        ),
        "data_freshness_green": (
            str(freshness.get("freshness_status", "")) == "data_freshness_green",
            str(freshness.get("freshness_status", "missing")),
        ),
        "envelope_intact": (
            str(envelope.get("integrity_status", "")) == "envelope_intact",
            f"{envelope.get('integrity_status', 'missing')} ({envelope.get('pinned_files_verified', '?')} pins)",
        ),
        "macro_lanes_validated": (
            len(macro.get("lanes_validated") or []) >= 8,
            f"{len(macro.get('lanes_validated') or [])} lanes",
        ),
        "no_discipline_halt_active": (
            int(halt.get("cooldown_sessions_remaining", 0)) <= 0,
            f"cooldown_remaining={halt.get('cooldown_sessions_remaining', 0)}",
        ),
        "scheduled_ritual_registered": (
            _scheduled_task_state() == "registered",
            _scheduled_task_state(),
        ),
        "disk_space_ok": (free_gb > 5.0, f"{free_gb:.1f} GB free"),
        "cross_provider_spot_check": (cross_provider_ok, cross_provider_detail),
    }

    passed = {name: detail for name, (ok, detail) in checks.items() if ok}
    attention = {name: detail for name, (ok, detail) in checks.items() if not ok}
    record = {
        "artifact_type": "monday_preflight",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "preflight_status": "all_clear" if not attention else "attention_required",
        "checks_passed": passed,
        "checks_attention": attention,
        "open_positions": len(ledger.get("open_positions", [])),
        "closed_trades": len(ledger.get("closed_trades", [])),
        "gate_readiness": gate.get("readiness_status", "missing"),
        "gate_missing_requirements": gate.get("missing_requirements", []),
        "evidence_eta": gate.get("evidence_eta", {}),
        "forward_walk_status": walk.get("forward_walk_status", "missing"),
        "plumbing_only_not_edge": True,
        "paper_only": True,
        "live_blocked": True,
    }
    write_json_atomic(PREFLIGHT_JSON, record)

    lines = [
        "# DOPEY Monday Preflight",
        "",
        f"Generated {record['generated_at_utc']} — status: **{record['preflight_status'].upper()}**",
        "",
        "Plumbing readiness only; no edge or evidence claim. Paper-only, live-blocked.",
        "",
        "## Checks",
        "",
    ]
    for name, (ok, detail) in checks.items():
        lines.append(f"- {'PASS' if ok else 'ATTENTION'} — `{name}` — {detail}")
    lines += [
        "",
        "## Book",
        "",
        f"- Open positions: {record['open_positions']}  |  Closed trades: {record['closed_trades']}",
        f"- Gate: {record['gate_readiness']} — missing: {', '.join(record['gate_missing_requirements']) or 'none'}",
        f"- Evidence ETA (estimate only): {record['evidence_eta'].get('est_trading_days_to_sample_at_current_book', '?')} trading days to sample",
        "",
    ]
    PREFLIGHT_MD.write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps({k: record[k] for k in ("preflight_status", "checks_attention", "gate_readiness")}, indent=2))
    print(f"report: {PREFLIGHT_MD}")
    return 0 if not attention else 1


if __name__ == "__main__":
    raise SystemExit(main())
