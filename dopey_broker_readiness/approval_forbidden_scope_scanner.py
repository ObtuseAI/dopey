"""Fixture-only scanner for forbidden approval scope expansions."""
from __future__ import annotations

import re
from typing import Any

from .broker_readiness_models import stable_hash


FORBIDDEN_SCOPE_TERMS: tuple[dict[str, str], ...] = (
    {"term_id": "live_trading", "phrase": "live trading", "category": "live_trading", "reason_code": "approval_mentions_live_trading"},
    {"term_id": "live_orders", "phrase": "live orders", "category": "live_trading", "reason_code": "approval_mentions_live_orders"},
    {"term_id": "place_order", "phrase": "place order", "category": "order_placement", "reason_code": "approval_mentions_order_placement"},
    {"term_id": "place_orders", "phrase": "place orders", "category": "order_placement", "reason_code": "approval_mentions_order_placement"},
    {"term_id": "place_trades", "phrase": "place trades", "category": "order_placement", "reason_code": "approval_mentions_order_placement"},
    {"term_id": "order_placement", "phrase": "order placement", "category": "order_placement", "reason_code": "approval_mentions_order_placement"},
    {"term_id": "cancel_order", "phrase": "cancel order", "category": "order_cancellation", "reason_code": "approval_mentions_order_cancellation"},
    {"term_id": "cancel_orders", "phrase": "cancel orders", "category": "order_cancellation", "reason_code": "approval_mentions_order_cancellation"},
    {"term_id": "order_cancellation", "phrase": "order cancellation", "category": "order_cancellation", "reason_code": "approval_mentions_order_cancellation"},
    {"term_id": "broker_execution", "phrase": "broker execution", "category": "broker_execute", "reason_code": "approval_expands_to_broker_execution"},
    {"term_id": "broker_write", "phrase": "broker write", "category": "broker_execute", "reason_code": "approval_expands_to_write_access"},
    {"term_id": "broker_write_access", "phrase": "broker write access", "category": "broker_execute", "reason_code": "approval_expands_to_write_access"},
    {"term_id": "broker_connection", "phrase": "broker connection", "category": "broker_execute", "reason_code": "approval_expands_to_broker_connection"},
    {"term_id": "connect_to_broker", "phrase": "connect to broker", "category": "broker_execute", "reason_code": "approval_expands_to_broker_connection"},
    {"term_id": "credentials", "phrase": "credentials", "category": "credential", "reason_code": "approval_mentions_credentials"},
    {"term_id": "credential", "phrase": "credential", "category": "credential", "reason_code": "approval_mentions_credentials"},
    {"term_id": "store_credentials", "phrase": "store credentials", "category": "credential", "reason_code": "approval_mentions_credential_storage"},
    {"term_id": "token", "phrase": "token", "category": "credential", "reason_code": "approval_mentions_token"},
    {"term_id": "api_key", "phrase": "api key", "category": "credential", "reason_code": "approval_mentions_api_key"},
    {"term_id": "env_file", "phrase": ".env", "category": "credential", "reason_code": "approval_mentions_env_file"},
    {"term_id": "account_balance", "phrase": "account balance", "category": "real_sizing", "reason_code": "approval_mentions_account_balance"},
    {"term_id": "buying_power", "phrase": "buying power", "category": "real_sizing", "reason_code": "approval_mentions_buying_power"},
    {"term_id": "real_sizing", "phrase": "real sizing", "category": "real_sizing", "reason_code": "approval_mentions_real_sizing"},
    {"term_id": "capital_reference", "phrase": "real capital", "category": "real_sizing", "reason_code": "approval_mentions_real_capital"},
    {"term_id": "scheduler", "phrase": "scheduler", "category": "scheduler", "reason_code": "approval_mentions_scheduler"},
    {"term_id": "cron", "phrase": "cron", "category": "scheduler", "reason_code": "approval_mentions_scheduler"},
    {"term_id": "daemon", "phrase": "daemon", "category": "scheduler", "reason_code": "approval_mentions_scheduler"},
    {"term_id": "autonomous_live", "phrase": "autonomous live", "category": "autonomous_loop", "reason_code": "approval_mentions_autonomous_live_trading"},
    {"term_id": "autonomous_live_trading", "phrase": "autonomous live trading", "category": "autonomous_loop", "reason_code": "approval_mentions_autonomous_live_trading"},
    {"term_id": "robinhood_mcp_execution", "phrase": "robinhood mcp execution", "category": "broker_execute", "reason_code": "approval_mentions_robinhood_mcp_execution"},
    {"term_id": "robinhood_mcp_write", "phrase": "robinhood mcp write", "category": "broker_execute", "reason_code": "approval_mentions_robinhood_mcp_execution"},
    {"term_id": "network_market_data", "phrase": "network market data", "category": "network_market_data", "reason_code": "approval_mentions_network_market_data"},
    {"term_id": "scrape", "phrase": "scrape", "category": "network_market_data", "reason_code": "approval_mentions_market_data_scrape"},
    {"term_id": "sell_to_open", "phrase": "sell-to-open", "category": "order_placement", "reason_code": "approval_mentions_sell_to_open"},
    {"term_id": "sell_to_open_spaces", "phrase": "sell to open", "category": "order_placement", "reason_code": "approval_mentions_sell_to_open"},
    {"term_id": "naked_option", "phrase": "naked option", "category": "order_placement", "reason_code": "approval_mentions_naked_option"},
    {"term_id": "uncovered", "phrase": "uncovered", "category": "order_placement", "reason_code": "approval_mentions_uncovered_writing"},
    {"term_id": "spread_execution", "phrase": "spread execution", "category": "order_placement", "reason_code": "approval_mentions_spread_execution"},
)
COMMAND_INJECTION_PATTERN = re.compile(r"(?:;|\|\||&&|`|\$\(|\bpowershell\b|\bcmd\b|\bcurl\b|\bwget\b|\bpython\s+-m\b)", re.IGNORECASE)
PATH_TOKEN_PATTERN = re.compile(r"(?:[A-Za-z]:\\|/[^ ]{2,}|token_path|secret_path|api_key_path)", re.IGNORECASE)


def forbidden_scope_term_library() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for term in FORBIDDEN_SCOPE_TERMS:
        seed = {**term, "terminal_block": True, "paper_only": True, "live_blocked": True}
        records.append({**seed, "term_hash": stable_hash(seed)})
    return records


def scan_forbidden_scope_terms(operator_text: str) -> list[dict[str, str]]:
    lowered = operator_text.lower()
    matches: list[dict[str, str]] = []
    seen: set[str] = set()
    for term in FORBIDDEN_SCOPE_TERMS:
        phrase = term["phrase"].lower()
        if phrase in lowered and term["term_id"] not in seen:
            matches.append(dict(term))
            seen.add(term["term_id"])
    if "\n" in operator_text and COMMAND_INJECTION_PATTERN.search(operator_text):
        matches.append({
            "term_id": "hidden_newline_command",
            "phrase": "hidden newline command",
            "category": "command_injection",
            "reason_code": "approval_contains_hidden_newline_command",
        })
    elif COMMAND_INJECTION_PATTERN.search(operator_text):
        matches.append({
            "term_id": "command_injection_like_text",
            "phrase": "command injection-like text",
            "category": "command_injection",
            "reason_code": "approval_contains_command_injection_like_text",
        })
    if PATH_TOKEN_PATTERN.search(operator_text) and ("token" in lowered or "secret" in lowered or "key" in lowered):
        matches.append({
            "term_id": "path_token_reference",
            "phrase": "path/token reference",
            "category": "credential",
            "reason_code": "approval_mentions_path_token_reference",
        })
    return _dedupe_matches(matches)


def forbidden_scope_flags(matches: list[dict[str, str]]) -> dict[str, bool]:
    categories = {match["category"] for match in matches}
    return {
        "credential_scope_detected": "credential" in categories,
        "live_trading_scope_detected": "live_trading" in categories or "autonomous_loop" in categories,
        "order_placement_scope_detected": "order_placement" in categories,
        "order_cancellation_scope_detected": "order_cancellation" in categories,
        "scheduler_scope_detected": "scheduler" in categories,
        "autonomous_loop_scope_detected": "autonomous_loop" in categories,
        "real_sizing_scope_detected": "real_sizing" in categories,
        "broker_execute_scope_detected": "broker_execute" in categories,
        "command_injection_scope_detected": "command_injection" in categories,
        "network_market_data_scope_detected": "network_market_data" in categories,
    }


def _dedupe_matches(matches: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in matches:
        key = match["term_id"]
        if key in seen:
            continue
        output.append(match)
        seen.add(key)
    return output
