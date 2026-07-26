"""V7 live gate (Workstream M).

Live trading remains disabled regardless of V7 breakthrough status.

Required:
- live_gate_status = disabled_live_gate_locked
- live_trading_enabled = false
- broker_connection_enabled = false
- real_order_enabled = false
- credentials_present = false
- official Robinhood market data allowed for research only
- unofficial Robinhood API / scraping / reverse-auth blocked
- Robinhood live trading false
- thresholds never lowered (MIN_BREAKTHROUGH_PF stays at 1.10)
- no-trade-only breakthroughs blocked from live promotion
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_autonomy.champion_hardening_common import live_safety_fields, robinhood_policy_fields
from dopey_autonomy.public_champion_common import (
    LIVE_GATE_ROOT,
    record_with_hash,
    write_jsonl_file,
    write_summary_with_hash,
)
from dopey_autonomy.signal_research_v7_common import (
    BREAKTHROUGH_V7_PATH,
    GATE_V7_SUMMARY_PATH,
    MIN_BREAKTHROUGH_PF,
    RESEARCH_V7_VERSION,
    utc_now_iso,
)


__all__ = ["run_public_signal_research_live_gate_status_v7"]


LIVE_GATE_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v7.json"
BLOCKERS_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_blockers_v7.jsonl"
PROOF_PATH = LIVE_GATE_ROOT / "public_signal_research_live_gate_proof_v7.jsonl"


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


def _has_no_trade_only_breakthrough(breakthroughs: list[dict[str, object]]) -> bool:
    for record in breakthroughs:
        if not isinstance(record, dict):
            continue
        if record.get("no_trade_only") is True or record.get("trade_active") is False:
            return True
    return False


def run_public_signal_research_live_gate_status_v7() -> dict[str, object]:
    breakthroughs = _read_jsonl_safe(BREAKTHROUGH_V7_PATH)
    gate = _read_json_safe(GATE_V7_SUMMARY_PATH)

    breakthrough_count = int(gate.get("breakthrough_candidate_count", 0)) if gate else 0
    watchlist_count = int(gate.get("watchlist_candidate_count", 0)) if gate else 0

    blockers: list[dict[str, object]] = [
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v7",
            "blocker": "v7_live_disabled_by_design",
            "detail": "V7 is a research / paper-only bundle. Live trading is locked.",
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v7",
            "blocker": "no_broker_connection",
            "detail": "No broker connection permitted in V7.",
            "broker_connection_enabled": False,
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v7",
            "blocker": "no_real_orders",
            "detail": "No real orders permitted in V7.",
            "real_order_enabled": False,
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v7",
            "blocker": "no_credentials",
            "detail": "No .env, no credentials, no hidden secrets.",
            "credentials_present": False,
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v7",
            "blocker": "robinhood_unofficial_blocked",
            "detail": "Unofficial Robinhood API, scraping, reverse-auth all blocked.",
            "unofficial_robinhood_api_blocked": True,
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v7",
            "blocker": "robinhood_official_market_data_allowed",
            "detail": "Official Robinhood market data feeds are allowed for research only.",
            "official_robinhood_market_data_allowed": True,
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v7",
            "blocker": "thresholds_never_lowered",
            "detail": f"MIN_BREAKTHROUGH_PF remains at {MIN_BREAKTHROUGH_PF:.2f}; no threshold reduction.",
            "min_breakthrough_pf": float(MIN_BREAKTHROUGH_PF),
            "thresholds_lowered": False,
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
        {
            "artifact_type": "public_signal_research_live_gate_blocker_v7",
            "blocker": "no_trade_only_breakthroughs_blocked",
            "detail": "No-trade-only breakthroughs are blocked from live promotion.",
            "no_trade_only_breakthroughs_blocked": True,
            "live_trading_enabled": False,
            **live_safety_fields(),
            **robinhood_policy_fields(),
        },
    ]

    if not breakthroughs:
        blockers.append(
            {
                "artifact_type": "public_signal_research_live_gate_blocker_v7",
                "blocker": "no_breakthrough_candidates",
                "detail": "V7 produced 0 breakthrough candidates. No live promotion path.",
                "breakthrough_candidate_count": breakthrough_count,
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )
    elif _has_no_trade_only_breakthrough(breakthroughs):
        blockers.append(
            {
                "artifact_type": "public_signal_research_live_gate_blocker_v7",
                "blocker": "no_trade_only_breakthrough_detected",
                "detail": "At least one breakthrough candidate is no-trade-only; live promotion blocked.",
                "breakthrough_candidate_count": breakthrough_count,
                "live_trading_enabled": False,
                **live_safety_fields(),
                **robinhood_policy_fields(),
            }
        )

    write_jsonl_file(BLOCKERS_PATH, [record_with_hash(b, "record_hash") for b in blockers])

    summary = {
        "artifact_type": "public_signal_research_live_gate_status_v7",
        "public_signal_research_v7_version": RESEARCH_V7_VERSION,
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
        "breakthrough_candidate_count": breakthrough_count,
        "watchlist_candidate_count": watchlist_count,
        "v7_min_breakthrough_pf": float(MIN_BREAKTHROUGH_PF),
        "thresholds_lowered": False,
        "public_data_only": True,
        "paper_only": True,
        "live_blocked": True,
        "no_trade_only_breakthroughs_blocked": True,
        "timestamp": utc_now_iso(),
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_summary_with_hash(LIVE_GATE_PATH, summary)

    proof_record = {
        "artifact_type": "public_signal_research_live_gate_proof_v7",
        "live_gate_status": summary["live_gate_status"],
        "live_trading_enabled": False,
        "blocker_count": summary["blocker_count"],
        "breakthrough_candidate_count": breakthrough_count,
        "watchlist_candidate_count": watchlist_count,
        "v7_min_breakthrough_pf": float(MIN_BREAKTHROUGH_PF),
        "thresholds_lowered": False,
        "no_trade_only_breakthroughs_blocked": True,
        **live_safety_fields(),
        **robinhood_policy_fields(),
    }
    write_jsonl_file(PROOF_PATH, [record_with_hash(proof_record, "proof_hash")])
    return summary


if __name__ == "__main__":
    import json as _json

    print(_json.dumps(run_public_signal_research_live_gate_status_v7(), indent=2, sort_keys=True, default=str))
