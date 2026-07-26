"""V5 live gate (Workstream N).

Even if V5 breakthroughs emerge, live remains disabled.

Required:
- live_gate_status = disabled_live_gate_locked
- live_trading_enabled = false
- broker_connection_enabled = false
- real_order_enabled = false
- credentials_present = false
- official Robinhood market data allowed
- unofficial Robinhood blocked
- Robinhood live trading false
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import record_with_hash, write_jsonl_file, write_summary_with_hash
from dopey_autonomy.signal_research_v5_common import (
    BREAKTHROUGH_V5_PATH,
    GATE_V5_SUMMARY_PATH,
    LIVE_GATE_ROOT,
    RESEARCH_V5_VERSION,
    utc_now_iso,
)
from dopey_wealth_engine.common import REPO_ROOT


__all__ = ["run_public_signal_research_live_gate_status_v5"]


LIVE_GATE_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v5.json"
BLOCKERS_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_blockers_v5.jsonl"
PROOF_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_proof_v5.jsonl"


def _read_jsonl_safe(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    out: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return out


def _read_json_safe(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def run_public_signal_research_live_gate_status_v5() -> dict[str, object]:
    breakthroughs = _read_jsonl_safe(BREAKTHROUGH_V5_PATH)
    gate = _read_json_safe(GATE_V5_SUMMARY_PATH)

    # Blockers (always present regardless of breakthrough)
    blockers: list[dict[str, object]] = [
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v5",
            "blocker": "v5_live_disabled_by_design",
            "detail": "V5 is a research / paper-only bundle. Live trading is locked.",
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v5",
            "blocker": "no_broker_connection",
            "detail": "No broker connection permitted in V5.",
            "broker_connection_enabled": False,
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v5",
            "blocker": "no_real_orders",
            "detail": "No real orders permitted in V5.",
            "real_order_enabled": False,
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v5",
            "blocker": "no_credentials",
            "detail": "No .env, no credentials, no hidden secrets.",
            "credentials_present": False,
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v5",
            "blocker": "robinhood_unofficial_blocked",
            "detail": "Unofficial Robinhood API, scraping, reverse-auth all blocked.",
            "unofficial_robinhood_api_blocked": True,
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
    ]
    if not breakthroughs:
        blockers.append(
            {
                "artifact_type": "public_signal_research_live_gate_blocker_v5",
                "blocker": "no_breakthrough_candidates",
                "detail": "V5 produced 0 breakthrough candidates. No live promotion path.",
                "breakthrough_candidate_count": int(gate.get("breakthrough_candidate_count", 0)),
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )

    write_jsonl_file(BLOCKERS_PATH, [record_with_hash(b, "record_hash") for b in blockers])

    summary = {
        "artifact_type": "public_signal_research_live_gate_status_v5",
        "public_signal_research_v5_version": RESEARCH_V5_VERSION,
        "live_gate_status": "disabled_live_gate_locked",
        "live_trading_enabled": False,
        "broker_connection_enabled": False,
        "real_order_enabled": False,
        "credentials_present": False,
        "env_present": False,
        "official_robinhood_market_data_allowed": True,
        "unofficial_robinhood_api_blocked": True,
        "robinhood_scraping_blocked": True,
        "robinhood_reverse_auth_blocked": True,
        "robinhood_live_trading_enabled": False,
        "blocker_count": len(blockers),
        "breakthrough_candidate_count": int(gate.get("breakthrough_candidate_count", 0)),
        "v5_min_breakthrough_pf": 1.10,
        "thresholds_lowered": False,
        "public_data_only": True,
        "paper_only": True,
        "live_blocked": True,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(LIVE_GATE_PATH, summary)

    # Proof
    proof_record = {
        "artifact_type": "public_signal_research_live_gate_proof_v5",
        "live_gate_status": summary["live_gate_status"],
        "live_trading_enabled": False,
        "blocker_count": summary["blocker_count"],
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(PROOF_PATH, [record_with_hash(proof_record, "proof_hash")])
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_public_signal_research_live_gate_status_v5(), indent=2, sort_keys=True, default=str))
