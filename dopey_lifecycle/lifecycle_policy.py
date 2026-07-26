"""Policy checks for offline active option lifecycle simulation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .lifecycle_models import ALLOWED_OPTION_TYPES, ALLOWED_STRATEGY_TYPES


REPO_ROOT = Path(__file__).resolve().parent.parent
LIFECYCLE_FIXTURE_DIR = REPO_ROOT / "dopey_data" / "fixtures" / "lifecycle"
LIFECYCLE_POLICY_FIXTURE_PATH = LIFECYCLE_FIXTURE_DIR / "lifecycle_policy.json"


def default_lifecycle_policy() -> dict[str, Any]:
    return {
        "artifact_type": "lifecycle_policy",
        "policy_id": "dopey-active-option-lifecycle-policy-v1",
        "allowed_option_types": sorted(ALLOWED_OPTION_TYPES),
        "allowed_strategy_types": sorted(ALLOWED_STRATEGY_TYPES),
        "buy_to_open_only": True,
        "sell_to_open_allowed": False,
        "naked_option_allowed": False,
        "undefined_risk_allowed": False,
        "unsupported_spread_allowed": False,
        "normal_same_day_close_allowed": False,
        "zero_dte_special_lifecycle_required": True,
        "zero_dte_special_close_requires_reason": True,
        "zero_dte_special_close_requires_liquidity": True,
        "zero_dte_special_close_requires_risk_cap": True,
        "swing_close_requires_next_day_or_later": True,
        "paperbroker_override_allowed": False,
        "terminal_block_auto_recovery_allowed": False,
        "full_suite_timeout_recorded_as_pass": False,
        "paper_only": True,
        "live_blocked": True,
        "no_real_market_data": True,
        "no_broker": True,
        "no_real_sizing": True,
        "no_scheduler": True,
        "no_credentials": True,
    }


def load_lifecycle_policy(path: Path | str = LIFECYCLE_POLICY_FIXTURE_PATH) -> dict[str, Any]:
    target = Path(path)
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    return default_lifecycle_policy()


def evaluate_lifecycle_case(case: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    reason_codes: list[str] = []
    option_type = str(case.get("option_type", ""))
    strategy_type = str(case.get("strategy_type", ""))
    action = str(case.get("open_action", "buy_to_open"))
    structure = str(case.get("structure", "long_call" if option_type == "call" else "long_put"))
    if option_type not in policy["allowed_option_types"]:
        reason_codes.append("unsupported_option_type_rejected")
    if strategy_type not in policy["allowed_strategy_types"]:
        reason_codes.append("unsupported_strategy_type_rejected")
    if action == "sell_to_open" or bool(case.get("sell_to_open_attempt", False)):
        reason_codes.append("sell_to_open_rejected")
    if bool(case.get("naked_option_attempt", False)):
        reason_codes.append("naked_option_sale_rejected")
    if bool(case.get("unsupported_spread_attempt", False)) or structure not in {"long_call", "long_put"}:
        reason_codes.append("unsupported_spread_rejected")
    if bool(case.get("undefined_risk_attempt", False)) or case.get("defined_risk", True) is not True:
        reason_codes.append("undefined_risk_structure_rejected")
    terminal_fields = {
        "live_flag_injection": "live_flag_injection_terminal_block",
        "broker_path_injection": "broker_path_injection_terminal_block",
        "credential_reference": "credential_reference_terminal_block",
        "scheduler_emergence": "scheduler_emergence_terminal_block",
        "real_sizing_reference": "real_sizing_reference_terminal_block",
        "full_suite_timeout_misclassified_as_pass": "full_suite_timeout_misclassified_as_pass_terminal_block",
        "paperbroker_override_attempt": "paperbroker_override_terminal_block",
        "terminal_block_auto_recovery_attempt": "terminal_block_auto_recovery_rejected",
    }
    for field_name, reason_code in terminal_fields.items():
        if bool(case.get(field_name, False)):
            reason_codes.append(reason_code)
    terminal = any(code.endswith("terminal_block") or "terminal_block" in code for code in reason_codes)
    return {
        "allowed": not reason_codes,
        "status": "terminal_block" if terminal else ("rejected" if reason_codes else "approved"),
        "reason_codes": reason_codes,
        "paper_only": True,
        "live_blocked": True,
    }
