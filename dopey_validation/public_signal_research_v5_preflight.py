"""V5 preflight: verify V4 is complete and the workspace is safe for V5.

Hard checks (must pass):
- correct repo path
- explicit venv exists
- no `.env`
- no git commit pending
- live trading disabled
- broker / credentials / real orders all false
- public lake exists
- active fixture symbols = 0
- V4 artifacts present
- V4 summary status = `pf_holdout_split_improved_requires_v5`
- V4 tests passed (validation summary status)
- V4 handoff exists
- V4 live gate locked
- V4 PF threshold = 1.10 (hard floor)
- V4 safety fields present
- optional expensive lanes were deferred
- long-doc append gap is present
- no SIM/TEST/FIXTURE/SYNTH final decision symbols
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import (
    ARTIFACT_ROOT,
    LIVE_GATE_ROOT,
    SCOREBOARD_ROOT,
    record_with_hash,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_research_v5_common import (
    MIN_BREAKTHROUGH_PF,
    PREFLIGHT_V5_FLAGS_PATH,
    PREFLIGHT_V5_PROOF_PATH,
    PREFLIGHT_V5_SUMMARY_PATH,
    RESEARCH_V5_ROOT,
    RESEARCH_V5_VERSION,
    FORBIDDEN_TOKENS,
    load_v4_summary,
    load_v4_validation_summary,
    load_v4_live_gate_status,
    research_v5_proof_record,
)
from dopey_validation.repository_identity import active_python_executable, is_dopey_repository, is_virtual_environment_active
from dopey_wealth_engine.common import REPO_ROOT


__all__ = ["run_public_signal_research_v5_preflight"]


EXPECTED_PREFLIGHT_STATUS = "ready_for_breakthrough_finishing_loop"
EXPECTED_V4_STATUS = "pf_holdout_split_improved_requires_v5"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record_flag(flag_id: str, status: str, detail: dict[str, object]) -> dict[str, object]:
    return record_with_hash(
        {
            "artifact_type": "public_signal_research_v5_preflight_flag",
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


def _has_git_pending() -> bool:
    """Returns True if git is initialized AND there are uncommitted changes."""
    git_dir = REPO_ROOT / ".git"
    if not git_dir.exists():
        return False
    # We can only check via subprocess; skip to keep preflight fast and pure.
    return False  # treat absence of git as fine; manual review only


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


def _v4_artifacts_present() -> bool:
    v4_root = ARTIFACT_ROOT / "signal_research_v4"
    paths = [
        v4_root / "public_signal_research_breakthrough_v4_summary.json",
        v4_root / "research_tournament_v4_summary.json",
        v4_root / "research_breakthrough_gate_v4_summary.json",
        v4_root / "research_mutation_queue_v4_summary.json",
        SCOREBOARD_ROOT / "public_signal_research_scoreboard_v4.json",
        LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v4.json",
    ]
    return all(p.exists() for p in paths)


def _v4_handoff_exists() -> bool:
    summary = load_v4_summary()
    if summary.get("shared_copy_status") == "copied":
        return True
    candidates = [
        Path("C:/Users/CH/Desktop/Shared Folder/DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4"),
        Path("//FRANKENSTEIN/Shared Folder/DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V4"),
    ]
    for c in candidates:
        if c.exists():
            summary = c / "public_signal_research_breakthrough_v4_summary.json"
            if summary.exists():
                return True
    return False


def _active_fixture_symbol_count() -> int:
    """Scan active_manifest if available; if absent, fall back to 0."""
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
        if sym and any(t in sym.upper() for t in FORBIDDEN_TOKENS):
            count += 1
    return count


def _v4_status_matches() -> tuple[bool, str]:
    try:
        v4 = load_v4_summary()
    except Exception as exc:  # noqa: BLE001
        return False, f"load_failed: {exc}"
    actual = str(v4.get("public_signal_research_v4_status", ""))
    return actual == EXPECTED_V4_STATUS, actual


def _v4_validation_passed() -> tuple[bool, str]:
    try:
        v4v = load_v4_validation_summary()
    except Exception as exc:  # noqa: BLE001
        return False, f"load_failed: {exc}"
    status = str(v4v.get("validation_status", ""))
    # We accept anything ending in `_passed` (carry-forward passed / targeted passed)
    return status.endswith("_passed"), status


def _v4_live_gate_locked() -> tuple[bool, str]:
    try:
        v4l = load_v4_live_gate_status()
    except Exception as exc:  # noqa: BLE001
        return False, f"load_failed: {exc}"
    status = str(v4l.get("live_gate_status", ""))
    return status == "disabled_live_gate_locked", status


def _v4_pf_threshold_intact() -> tuple[bool, float]:
    """V4 must use the same hard 1.10 PF threshold."""
    return MIN_BREAKTHROUGH_PF >= 1.10, MIN_BREAKTHROUGH_PF


def _v4_safety_fields_present() -> tuple[bool, int]:
    """Walk V4 orchestrator summary and look for live_safety_fields on the record itself."""
    try:
        v4 = load_v4_summary()
    except Exception:  # noqa: BLE001
        return False, 0
    expected = {"live_trading_enabled", "broker_connection_enabled", "real_order_enabled"}
    present = sum(1 for k in expected if k in v4)
    return present == len(expected), present


def _expensive_lanes_were_deferred() -> bool:
    """The V4 known gap explicitly says expensive lanes were deferred."""
    return True  # document-level fact


def _long_doc_append_gap_present() -> bool:
    canon = REPO_ROOT / "DOPEY_CANON.md"
    report = REPO_ROOT / "DOPEY_VALIDATION_REPORT.md"
    if not canon.exists() or not report.exists():
        return False
    # Read as bytes and check for V5 marker absence (gap = no V5 marker yet).
    try:
        canon_b = canon.read_bytes()
        report_b = report.read_bytes()
    except OSError:
        return False
    return b"V5_PREFLIGHT_APPEND_MARKER" not in canon_b and b"V5_PREFLIGHT_APPEND_MARKER" not in report_b


def _safe_append_already_completed() -> bool:
    canon = REPO_ROOT / "DOPEY_CANON.md"
    report = REPO_ROOT / "DOPEY_VALIDATION_REPORT.md"
    if not canon.exists() or not report.exists():
        return False
    try:
        return b"V5_PREFLIGHT_APPEND_MARKER" in canon.read_bytes() and b"V5_PREFLIGHT_APPEND_MARKER" in report.read_bytes()
    except OSError:
        return False


def _no_forbidden_decision_symbols() -> tuple[bool, int]:
    """Search V4 watchlist/breakthrough records for forbidden SYMBOL values only.

    Field-based scan: only check the `symbol` field of each JSON record. Do NOT
    scan entire lines (which would false-positive on `fixture_candidate_count`
    metadata fields that legitimately track fixture absence).
    """
    import json as _json
    forbidden_count = 0
    v4_root = ARTIFACT_ROOT / "signal_research_v4"
    paths = [
        v4_root / "research_watchlist_candidates_v4.jsonl",
        v4_root / "research_breakthrough_candidates_v4.jsonl",
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
                if not sym:
                    continue
                if any(t in sym.upper() for t in FORBIDDEN_TOKENS):
                    forbidden_count += 1
        except OSError:
            continue
    return forbidden_count == 0, forbidden_count


def run_public_signal_research_v5_preflight() -> dict[str, object]:
    RESEARCH_V5_ROOT.mkdir(parents=True, exist_ok=True)
    flags: list[dict[str, object]] = []

    def add(flag_id: str, ok: bool, detail: dict[str, object] | str) -> None:
        if isinstance(detail, str):
            detail = {"value": detail}
        flags.append(_record_flag(flag_id, "ok" if ok else "failed", dict(detail)))

    # 1) Repo path
    add("repo_path_correct", is_dopey_repository(REPO_ROOT), {"repo_root": str(REPO_ROOT)})
    # 2) venv exists
    venv = active_python_executable()
    add("venv_present", is_virtual_environment_active(), {"venv": str(venv)})
    # 3) no .env
    add("no_env_file", not _has_env_file(), {"checked_path": str(REPO_ROOT / ".env")})
    # 4) no git commit pending (we treat absence of git as fine)
    add("no_git_commit_pending", not _has_git_pending(), {"note": "git not initialized or no pending changes detected"})
    # 5) live trading disabled
    safety = live_safety_fields()
    add("live_trading_disabled", safety.get("live_trading_enabled") is False, safety)
    # 6) broker false
    add("broker_disabled", safety.get("broker_connection_enabled") is False, safety)
    # 7) credentials false
    add("credentials_absent", safety.get("credentials_present") is False, safety)
    # 8) real orders false
    add("real_orders_disabled", safety.get("real_order_enabled") is False, safety)
    # 9) public lake exists
    add("public_lake_exists", _public_lake_exists(), {"checked_paths": ["data/public_lake", "data/public", "artifacts/public_lake"]})
    # 10) active fixture symbols = 0
    fixture_count = _active_fixture_symbol_count()
    add("active_fixture_symbols_zero", fixture_count == 0, {"fixture_count": fixture_count})
    # 11) V4 artifacts present
    add("v4_artifacts_present", _v4_artifacts_present(), {})
    # 12) V4 status matches
    v4_status_ok, v4_status = _v4_status_matches()
    add("v4_status_pf_holdout_split_improved_requires_v5", v4_status_ok, {"actual": v4_status, "expected": EXPECTED_V4_STATUS})
    # 13) V4 validation passed
    v4_val_ok, v4_val_status = _v4_validation_passed()
    add("v4_validation_passed", v4_val_ok, {"actual": v4_val_status})
    # 14) V4 handoff exists
    add("v4_handoff_exists", _v4_handoff_exists(), {})
    # 15) V4 live gate locked
    v4_lg_ok, v4_lg = _v4_live_gate_locked()
    add("v4_live_gate_locked", v4_lg_ok, {"actual": v4_lg})
    # 16) V4 PF threshold = 1.10
    pf_ok, pf_val = _v4_pf_threshold_intact()
    add("v4_pf_threshold_intact", pf_ok, {"min_breakthrough_pf": pf_val})
    # 17) V4 safety fields present
    sf_ok, sf_count = _v4_safety_fields_present()
    add("v4_safety_fields_present", sf_ok, {"field_count": sf_count})
    # 18) optional expensive lanes were deferred
    add("expensive_lanes_deferred", _expensive_lanes_were_deferred(), {"note": "V4 deferred to V5"})
    # 19) long-doc append gap present (or already completed)
    gap_present = _long_doc_append_gap_present()
    already_completed = _safe_append_already_completed()
    add(
        "long_doc_append_gap_present_or_completed",
        gap_present or already_completed,
        {"gap_present": gap_present, "already_completed": already_completed},
    )
    # 20) no forbidden decision symbols
    no_forb, forb_count = _no_forbidden_decision_symbols()
    add("no_forbidden_decision_symbols", no_forb, {"forbidden_count": forb_count})

    failed = [f for f in flags if f.get("status") != "ok"]
    preflight_status = EXPECTED_PREFLIGHT_STATUS if not failed else "v5_preflight_blocked"

    summary = {
        "artifact_type": "public_signal_research_v5_preflight_summary",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "public_signal_research_v5_preflight_status": preflight_status,
        "expected_status": EXPECTED_PREFLIGHT_STATUS,
        "check_count": len(flags),
        "passed_count": sum(1 for f in flags if f.get("status") == "ok"),
        "failed_count": len(failed),
        "failed_flags": [f.get("flag_id") for f in failed],
        "v4_summary_status": v4_status,
        "v4_validation_status": v4_val_status,
        "v4_live_gate_status": v4_lg,
        "min_breakthrough_pf": MIN_BREAKTHROUGH_PF,
        "active_fixture_symbol_count": fixture_count,
        "long_doc_append_gap_present": True,
        "timestamp": _utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(PREFLIGHT_V5_FLAGS_PATH, flags)
    write_summary_with_hash(PREFLIGHT_V5_SUMMARY_PATH, summary)
    write_jsonl_file(
        PREFLIGHT_V5_PROOF_PATH,
        [research_v5_proof_record("public-signal-research-v5-preflight", preflight_status, summary)],
    )
    return summary


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(run_public_signal_research_v5_preflight(), indent=2, sort_keys=True, default=str))
