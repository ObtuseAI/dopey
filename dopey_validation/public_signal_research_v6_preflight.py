"""V6 preflight: verify V5 is complete and the workspace is safe for V6.

Hard checks (must pass):
- correct repo path
- explicit venv exists
- no `.env`
- live trading disabled
- broker / credentials / real orders all false
- public lake exists
- active fixture symbols = 0
- V5 artifacts present
- V5 summary status = `pf_holdout_split_improved_requires_v6`
- V5 watchlist count = 6, breakthrough count = 0, PF above 1.10 count = 6
- V5 mutation queue count = 132
- top PF > 1.10 and top PnL recorded
- V5 live gate locked
- V5 handoff exists
- safety fields present
- threshold not lowered (MIN_BREAKTHROUGH_PF >= 1.10)
- no SIM/TEST/FIXTURE/SYNTH final decision symbols
- expensive lane timeout recorded honestly (timeout_recorded_as_pass false)
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import (
    ARTIFACT_ROOT,
    SCOREBOARD_ROOT,
    record_with_hash,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_research_v6_common import (
    MIN_BREAKTHROUGH_PF,
    PREFLIGHT_V6_FLAGS_PATH,
    PREFLIGHT_V6_PROOF_PATH,
    PREFLIGHT_V6_SUMMARY_PATH,
    RESEARCH_V6_ROOT,
    RESEARCH_V6_VERSION,
    V5_LIVE_GATE_PATH,
    is_forbidden_symbol,
    load_v5_expensive_lane_summary,
    load_v5_live_gate_status,
    load_v5_summary,
    load_v5_timeout_records,
    load_v5_validation_summary,
    load_v5_watchlist_records,
    research_v6_proof_record,
)
from dopey_validation.repository_identity import active_python_executable, is_dopey_repository, is_virtual_environment_active
from dopey_wealth_engine.common import REPO_ROOT


__all__ = ["run_public_signal_research_v6_preflight"]


EXPECTED_PREFLIGHT_STATUS = "ready_for_watchlist_breakthrough_repair"
EXPECTED_V5_STATUS = "pf_holdout_split_improved_requires_v6"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_flag(flag_id: str, status: str, detail: dict[str, object]) -> dict[str, object]:
    return record_with_hash(
        {
            "artifact_type": "public_signal_research_v6_preflight_flag",
            "flag_id": flag_id,
            "status": status,
            "detail": detail,
            "timestamp": _utc_now_iso(),
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
        "flag_hash",
    )


def _has_env_file() -> bool:
    return (REPO_ROOT / ".env").exists()


def _venv_exists() -> bool:
    return is_virtual_environment_active()


def _public_lake_exists() -> bool:
    candidates = [
        REPO_ROOT / "data" / "public_lake",
        REPO_ROOT / "data" / "public",
        ARTIFACT_ROOT / "public_lake",
        REPO_ROOT / "artifacts" / "public_lake",
        REPO_ROOT / "dopey_data" / "market_lake",
        REPO_ROOT / "dopey_data" / "real",
        REPO_ROOT / "dopey_data" / "open_autonomy",
    ]
    return any(p.exists() for p in candidates)


def _v5_artifacts_present() -> bool:
    from dopey_autonomy.signal_research_v6_common import (
        V5_GATE_SUMMARY_PATH,
        V5_MUTATION_QUEUE_PATH,
        V5_MUTATION_QUEUE_SUMMARY_PATH,
        V5_SUMMARY_PATH,
        V5_TIMEOUT_RECORDS_PATH,
        V5_VALIDATION_SUMMARY_PATH,
        V5_WATCHLIST_PATH,
    )

    paths = [
        V5_SUMMARY_PATH,
        V5_GATE_SUMMARY_PATH,
        V5_MUTATION_QUEUE_PATH,
        V5_MUTATION_QUEUE_SUMMARY_PATH,
        V5_WATCHLIST_PATH,
        V5_LIVE_GATE_PATH,
        V5_VALIDATION_SUMMARY_PATH,
        V5_TIMEOUT_RECORDS_PATH,
        SCOREBOARD_ROOT / "public_signal_research_scoreboard_v5.json",
    ]
    return all(p.exists() for p in paths)


def _v5_handoff_exists() -> bool:
    summary = load_v5_summary()
    if summary.get("shared_copy_status") == "copied":
        return True
    candidates = [
        Path("C:/Users/CH/Desktop/Shared Folder/DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5"),
        Path("//FRANKENSTEIN/Shared Folder/DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V5"),
    ]
    for c in candidates:
        if c.exists():
            summary = c / "public_signal_research_breakthrough_v5_summary.json"
            if summary.exists():
                return True
    return False


def _active_fixture_symbol_count() -> int:
    manifest_path = ARTIFACT_ROOT / "active_manifest.json"
    if not manifest_path.exists():
        return 0
    try:
        import json as _json

        manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    if isinstance(manifest, dict):
        rows = manifest.get("rows") or manifest.get("symbols") or []
    elif isinstance(manifest, list):
        rows = manifest
    else:
        rows = []
    count = 0
    for row in rows:
        sym = ""
        if isinstance(row, dict):
            sym = str(row.get("symbol", "") or row.get("ticker", "") or "")
        elif isinstance(row, str):
            sym = row
        if sym and is_forbidden_symbol(sym):
            count += 1
    return count


def _no_forbidden_decision_symbols() -> tuple[bool, int]:
    import json as _json

    forbidden_count = 0
    v5_root = ARTIFACT_ROOT / "signal_research_v5"
    paths = [
        v5_root / "research_watchlist_candidates_v5.jsonl",
        v5_root / "research_breakthrough_candidates_v5.jsonl",
    ]
    for p in paths:
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = _json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                sym = str(rec.get("symbol", "") or rec.get("ticker", "") or "")
                if sym and is_forbidden_symbol(sym):
                    forbidden_count += 1
        except OSError:
            continue
    return forbidden_count == 0, forbidden_count


def _timeout_recorded_honestly() -> tuple[bool, dict[str, object]]:
    v5 = load_v5_summary()
    expensive = load_v5_expensive_lane_summary()
    validation = load_v5_validation_summary()
    timeout_records = load_v5_timeout_records()
    checks = {
        "v5_summary_timeout_recorded_as_pass": not bool(v5.get("timeout_recorded_as_pass", True)),
        "expensive_lane_timeout_recorded_as_pass": not bool(expensive.get("timeout_recorded_as_pass", True)),
        "validation_timeout_recorded_as_pass": not bool(validation.get("timeout_recorded_as_pass", True)),
        "timeout_records_present": len(timeout_records) > 0,
    }
    ok = all(checks.values())
    return ok, checks


def run_public_signal_research_v6_preflight() -> dict[str, object]:
    RESEARCH_V6_ROOT.mkdir(parents=True, exist_ok=True)
    flags: list[dict[str, object]] = []

    def add(flag_id: str, ok: bool, detail: dict[str, object] | str) -> None:
        if isinstance(detail, str):
            detail = {"value": detail}
        flags.append(_record_flag(flag_id, "ok" if ok else "failed", dict(detail)))

    # 1) Repo path
    add("repo_path_correct", is_dopey_repository(REPO_ROOT), {"repo_root": str(REPO_ROOT)})
    # 2) venv exists
    add("venv_present", _venv_exists(), {"venv": str(active_python_executable())})
    # 3) no .env
    add("no_env_file", not _has_env_file(), {"checked_path": str(REPO_ROOT / ".env")})
    # 4) live trading disabled
    safety = live_safety_fields()
    add("live_trading_disabled", safety.get("live_trading_enabled") is False, safety)
    # 5) broker false
    add("broker_disabled", safety.get("broker_connection_enabled") is False, safety)
    # 6) credentials false
    add("credentials_absent", safety.get("credentials_present") is False, safety)
    # 7) real orders false
    add("real_orders_disabled", safety.get("real_order_enabled") is False, safety)
    # 8) public lake exists
    add("public_lake_exists", _public_lake_exists(), {"checked_paths": [str(p) for p in [
        REPO_ROOT / "data" / "public_lake",
        REPO_ROOT / "dopey_data" / "market_lake",
    ]]})
    # 9) active fixture symbols = 0
    fixture_count = _active_fixture_symbol_count()
    add("active_fixture_symbols_zero", fixture_count == 0, {"fixture_count": fixture_count})
    # 10) V5 artifacts present
    add("v5_artifacts_present", _v5_artifacts_present(), {})

    # 11) V5 summary status
    v5_summary = load_v5_summary()
    v5_status = str(v5_summary.get("public_signal_research_v5_status", ""))
    add(
        "v5_status_pf_holdout_split_improved_requires_v6",
        v5_status == EXPECTED_V5_STATUS,
        {"actual": v5_status, "expected": EXPECTED_V5_STATUS},
    )

    # 12) V5 watchlist count
    watchlist = load_v5_watchlist_records()
    watchlist_count = len(watchlist)
    add("v5_watchlist_count_6", watchlist_count == 6, {"watchlist_count": watchlist_count})

    # 13) V5 breakthrough count
    breakthrough_count = int(v5_summary.get("breakthrough_candidate_count", -1))
    add("v5_breakthrough_count_0", breakthrough_count == 0, {"breakthrough_count": breakthrough_count})

    # 14) PF above 1.10 count
    pf_above_count = int(v5_summary.get("pf_above_110_count", -1))
    add("v5_pf_above_110_count_6", pf_above_count == 6, {"pf_above_110_count": pf_above_count})

    # 15) V5 mutation queue count
    mutation_queue_count = int(v5_summary.get("v5_mutation_queue_count", -1))
    add("v5_mutation_queue_count_132", mutation_queue_count == 132, {"mutation_queue_count": mutation_queue_count})

    # 16) top PF > 1.10
    top_pf = float(v5_summary.get("top_profit_factor", 0.0))
    add("v5_top_pf_above_110", top_pf > MIN_BREAKTHROUGH_PF, {"top_profit_factor": top_pf})

    # 17) top PnL recorded
    top_pnl = v5_summary.get("top_net_pnl")
    add("v5_top_pnl_recorded", top_pnl is not None, {"top_net_pnl": top_pnl})

    # 18) V5 live gate locked
    live_gate = load_v5_live_gate_status()
    live_gate_status = str(live_gate.get("live_gate_status", ""))
    add("v5_live_gate_locked", live_gate_status == "disabled_live_gate_locked", {"actual": live_gate_status})

    # 19) V5 handoff exists
    add("v5_handoff_exists", _v5_handoff_exists(), {})

    # 20) safety fields present on V5 summary
    expected_safety = {"live_trading_enabled", "broker_connection_enabled", "real_order_enabled"}
    present_safety = sum(1 for k in expected_safety if k in v5_summary)
    add("v5_safety_fields_present", present_safety == len(expected_safety), {"field_count": present_safety})

    # 21) threshold not lowered
    threshold_ok = MIN_BREAKTHROUGH_PF >= 1.10
    thresholds_lowered = bool(v5_summary.get("thresholds_lowered", False))
    add(
        "v6_threshold_not_lowered",
        threshold_ok and not thresholds_lowered,
        {"min_breakthrough_pf": MIN_BREAKTHROUGH_PF, "thresholds_lowered": thresholds_lowered},
    )

    # 22) no forbidden decision symbols
    no_forb, forb_count = _no_forbidden_decision_symbols()
    add("no_forbidden_decision_symbols", no_forb, {"forbidden_count": forb_count})

    # 23) expensive lane timeout recorded honestly
    timeout_ok, timeout_detail = _timeout_recorded_honestly()
    add("expensive_lane_timeout_recorded_honestly", timeout_ok, timeout_detail)

    failed = [f for f in flags if f.get("status") != "ok"]
    preflight_status = EXPECTED_PREFLIGHT_STATUS if not failed else "v6_preflight_blocked"

    summary = {
        "artifact_type": "public_signal_research_v6_preflight_summary",
        "public_signal_research_v6_version": RESEARCH_V6_VERSION,
        "public_signal_research_v6_preflight_status": preflight_status,
        "expected_status": EXPECTED_PREFLIGHT_STATUS,
        "check_count": len(flags),
        "passed_count": sum(1 for f in flags if f.get("status") == "ok"),
        "failed_count": len(failed),
        "failed_flags": [f.get("flag_id") for f in failed],
        "v5_summary_status": v5_status,
        "watchlist_count": watchlist_count,
        "v5_watchlist_count": watchlist_count,
        "breakthrough_count": breakthrough_count,
        "v5_breakthrough_count": breakthrough_count,
        "pf_above_110_count": pf_above_count,
        "v5_pf_above_110_count": pf_above_count,
        "mutation_queue_count": mutation_queue_count,
        "v5_mutation_queue_count": mutation_queue_count,
        "top_profit_factor": top_pf,
        "top_net_pnl": top_pnl,
        "live_gate_status": live_gate_status,
        "v5_live_gate_status": live_gate_status,
        "v5_expensive_lane_timeout_recorded_as_pass": not bool(timeout_detail.get("expensive_lane_timeout_recorded_as_pass", True)),
        "v5_timeout_detail": timeout_detail,
        "active_fixture_symbol_count": fixture_count,
        "min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "thresholds_lowered": thresholds_lowered,
        "timestamp": _utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(PREFLIGHT_V6_FLAGS_PATH, flags)
    write_summary_with_hash(PREFLIGHT_V6_SUMMARY_PATH, summary)
    write_jsonl_file(
        PREFLIGHT_V6_PROOF_PATH,
        [research_v6_proof_record("public-signal-research-v6-preflight", preflight_status, summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_public_signal_research_v6_preflight(), indent=2, sort_keys=True, default=str))
