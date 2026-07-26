"""User-scoped control state for the DOPEY Live Branch."""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import platform
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Final


CONTROL_SCHEMA: Final[str] = "dopey-live-branch-control-v1"
CONTROL_CONFIRMATION: Final[str] = "owner_live_branch_control"
OFFICIAL_ROBINHOOD_MCP: Final[str] = "https://agent.robinhood.com/mcp/trading"


class LiveBranchControlError(RuntimeError):
    """Raised when Live Branch control state is missing or invalid."""


@dataclass(frozen=True)
class LiveBranchControl:
    schema_version: str
    mode: str
    account_label: str
    official_mcp_endpoint: str
    live_branch_enabled: bool
    stock_execution_enabled: bool
    options_execution_enabled: bool
    paper_twin_required: bool
    no_day_trading_enforced: bool
    use_full_available_balance: bool
    unofficial_broker_api_allowed: bool
    owner_authorization_id: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def default_live_branch_control() -> LiveBranchControl:
    # Fail closed: a missing control file must never silently re-arm live
    # trading. Execution stays disabled until the owner explicitly arms the
    # branch via set_live_branch_enabled with CONTROL_CONFIRMATION.
    return LiveBranchControl(
        schema_version=CONTROL_SCHEMA,
        mode="LIVE",
        account_label="agentic",
        official_mcp_endpoint=OFFICIAL_ROBINHOOD_MCP,
        live_branch_enabled=False,
        stock_execution_enabled=False,
        options_execution_enabled=False,
        paper_twin_required=True,
        no_day_trading_enforced=True,
        use_full_available_balance=True,
        unofficial_broker_api_allowed=False,
        owner_authorization_id=_machine_authorization_id(),
    )


def resolve_live_branch_control_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        raise LiveBranchControlError("LOCALAPPDATA is required for user-scoped Live Branch control")
    return Path(local_app_data).resolve() / "DOPEY" / "live-branch-control.json"


def _machine_authorization_id() -> str:
    material = "|".join(
        (
            platform.node(),
            getpass.getuser(),
            str(resolve_live_branch_control_path().parent),
        )
    )
    return "machine:" + hashlib.sha256(material.encode("utf-8")).hexdigest()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(encoded)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def _validated_control(payload: dict[str, Any]) -> LiveBranchControl:
    required = set(LiveBranchControl.__dataclass_fields__)
    missing = sorted(required - set(payload))
    unknown = sorted(set(payload) - required)
    if missing or unknown:
        raise LiveBranchControlError(
            f"Live Branch control schema mismatch: missing={missing}, unknown={unknown}"
        )
    control = LiveBranchControl(**payload)
    if control.schema_version != CONTROL_SCHEMA:
        raise LiveBranchControlError(
            f"Unsupported Live Branch control schema: {control.schema_version}"
        )
    if control.mode != "LIVE":
        raise LiveBranchControlError(f"Live Branch mode must be LIVE: actual={control.mode}")
    if control.official_mcp_endpoint != OFFICIAL_ROBINHOOD_MCP:
        raise LiveBranchControlError(
            "Live Branch must use Robinhood's official Trading MCP endpoint"
        )
    if control.unofficial_broker_api_allowed:
        raise LiveBranchControlError("Unofficial Robinhood APIs are prohibited")
    if not control.paper_twin_required or not control.no_day_trading_enforced:
        raise LiveBranchControlError(
            "Live Branch requires paper_twin_required=true and no_day_trading_enforced=true"
        )
    if control.owner_authorization_id != _machine_authorization_id():
        raise LiveBranchControlError(
            "Live Branch control is not authorized for this machine and user profile"
        )
    return control


def load_live_branch_control() -> LiveBranchControl:
    path = resolve_live_branch_control_path()
    if not path.exists():
        raise LiveBranchControlError(
            "Live Branch control is missing and remains disabled; use the explicit owner arming command"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LiveBranchControlError(
            f"Unable to read Live Branch control: path={path}, error={error}"
        ) from error
    if not isinstance(payload, dict) or not all(isinstance(key, str) for key in payload):
        raise LiveBranchControlError(f"Live Branch control must be a JSON object: path={path}")
    return _validated_control(payload)


def set_live_branch_enabled(enabled: bool, confirmation: str) -> LiveBranchControl:
    if type(enabled) is not bool:
        raise TypeError(f"enabled must be bool, received {type(enabled).__name__}")
    if confirmation != CONTROL_CONFIRMATION:
        raise LiveBranchControlError(
            f"Live Branch control requires confirmation={CONTROL_CONFIRMATION!r}"
        )
    path = resolve_live_branch_control_path()
    current = (
        load_live_branch_control()
        if path.exists()
        else default_live_branch_control()
    )
    updated = LiveBranchControl(
        **{
            **current.to_dict(),
            "live_branch_enabled": enabled,
            "stock_execution_enabled": enabled,
            # Re-arming never resurrects an old options permission. Options
            # always require their own explicit confirmation after the branch
            # is enabled, and disarming clears every execution switch.
            "options_execution_enabled": False,
        }
    )
    _atomic_write(path, updated.to_dict())
    return updated


def set_options_execution_enabled(enabled: bool, confirmation: str) -> LiveBranchControl:
    if type(enabled) is not bool:
        raise TypeError(f"enabled must be bool, received {type(enabled).__name__}")
    if confirmation != CONTROL_CONFIRMATION:
        raise LiveBranchControlError(
            f"Options control requires confirmation={CONTROL_CONFIRMATION!r}"
        )
    current = load_live_branch_control()
    if enabled and (
        not current.live_branch_enabled or not current.stock_execution_enabled
    ):
        raise LiveBranchControlError(
            "Options execution cannot be enabled while the Live Branch or stock execution is disabled"
        )
    updated = LiveBranchControl(**{**current.to_dict(), "options_execution_enabled": enabled})
    _atomic_write(resolve_live_branch_control_path(), updated.to_dict())
    return updated
