"""Sanitized desktop projection of DOPEY Live Branch control and evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dopey_live.control import LiveBranchControlError, load_live_branch_control
from dopey_live.ledger import ledger_path, latest_cycle_path, paper_twin_path, read_ledger


MAX_LIVE_CYCLE_AGE_SECONDS = 20 * 60


def _read_optional_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    decoded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(decoded, dict) or not all(isinstance(key, str) for key in decoded):
        raise ValueError(f"Live Branch state artifact must be an object: path={path}")
    return decoded


def _cycle_freshness(
    cycle: dict[str, Any],
    now_utc: datetime,
) -> tuple[str, float | None]:
    raw_generated_utc = cycle.get("generated_utc")
    if not cycle:
        return "missing", None
    if not isinstance(raw_generated_utc, str) or not raw_generated_utc:
        return "invalid_timestamp", None
    try:
        generated_utc = datetime.fromisoformat(raw_generated_utc)
    except ValueError:
        return "invalid_timestamp", None
    if generated_utc.tzinfo is None:
        return "invalid_timestamp", None
    age_seconds = (
        now_utc.astimezone(timezone.utc)
        - generated_utc.astimezone(timezone.utc)
    ).total_seconds()
    if age_seconds < -300:
        return "future_timestamp", round(age_seconds, 3)
    if age_seconds > MAX_LIVE_CYCLE_AGE_SECONDS:
        return "stale", round(age_seconds, 3)
    return "fresh", round(age_seconds, 3)


def build_live_branch_state(repository_root: Path) -> dict[str, Any]:
    try:
        control = load_live_branch_control()
        cycle = _read_optional_mapping(latest_cycle_path(repository_root))
        live_records = read_ledger(ledger_path(repository_root))
        twin_records = read_ledger(paper_twin_path(repository_root))
    except (OSError, json.JSONDecodeError, ValueError, LiveBranchControlError) as error:
        return {
            "schema_version": "dopey-desktop-live-branch-v1",
            "mode": "LIVE",
            "status": "fault",
            "error": str(error),
            "stock_execution_enabled": None,
            "options_execution_enabled": None,
            "official_robinhood_mcp": True,
            "authenticated": False,
        }
    account = cycle.get("account", {})
    account = account if isinstance(account, dict) else {}
    order_payloads = [
        record["payload"]
        for record in live_records
        if record.get("event_type") == "live_order_result"
        and isinstance(record.get("payload"), dict)
    ]
    placed_count = sum(payload.get("placed") is True for payload in order_payloads)
    authenticated = account.get("authenticated") is True
    cycle_status = str(cycle.get("cycle_status", "configured_awaiting_first_cycle"))
    cycle_freshness, cycle_age_seconds = _cycle_freshness(
        cycle,
        datetime.now(timezone.utc),
    )
    projected_status = (
        "fault"
        if cycle_freshness in {"invalid_timestamp", "future_timestamp"}
        else "stale"
        if cycle_freshness == "stale"
        else "live"
        if authenticated and control.live_branch_enabled
        else "configured"
    )
    return {
        "schema_version": "dopey-desktop-live-branch-v1",
        "mode": control.mode,
        "status": projected_status,
        "cycle_status": cycle_status,
        "generated_utc": cycle.get("generated_utc"),
        "cycle_freshness": cycle_freshness,
        "cycle_age_seconds": cycle_age_seconds,
        "max_cycle_age_seconds": MAX_LIVE_CYCLE_AGE_SECONDS,
        "account_label": control.account_label,
        "account_type": account.get("account_type"),
        "authenticated": authenticated,
        "official_robinhood_mcp": True,
        "official_mcp_endpoint": control.official_mcp_endpoint,
        "live_branch_enabled": control.live_branch_enabled,
        "stock_execution_enabled": control.stock_execution_enabled,
        "options_execution_capable": True,
        "options_execution_enabled": control.options_execution_enabled,
        "paper_twin_required": control.paper_twin_required,
        "no_day_trading_enforced": control.no_day_trading_enforced,
        "use_full_available_balance": control.use_full_available_balance,
        "market_open": cycle.get("market_open"),
        "market_date": cycle.get("market_date"),
        "buying_power_usd": account.get("buying_power_usd"),
        "total_equity_usd": account.get("total_equity_usd"),
        "equity_position_count": len(account.get("equity_positions", []))
        if isinstance(account.get("equity_positions", []), list)
        else None,
        "option_position_count": len(account.get("option_positions", []))
        if isinstance(account.get("option_positions", []), list)
        else None,
        "live_order_event_count": len(order_payloads),
        "placed_order_count": placed_count,
        "paper_twin_event_count": len(twin_records),
        "recent_orders": order_payloads[-12:],
        "owner_authorization_id": control.owner_authorization_id,
        "account_identifiers_redacted": True,
        "error": cycle.get("error"),
    }
