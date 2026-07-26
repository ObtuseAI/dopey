"""Native desktop host for the DOPEY Control Center.

The host deliberately loads one compiled local document and exposes one narrow
connector.  It does not start an HTTP server and does not expose filesystem,
process, broker, credential-readback, or order-construction APIs to the web
surface. Its only secret operation is a write-only Windows DPAPI key update.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
from pathlib import Path
from threading import RLock
from typing import Final, Protocol

import webview

from dopey_acceleration.provider_control import (
    ProviderControlError,
    provider_control_state,
    set_instrument_mode as set_provider_instrument_mode,
    set_provider_enabled,
    store_openrouter_api_key,
)
from dopey_analysis.two_coach_engine import (
    TwoCoachContractError,
    run_two_coach_review,
)
from dopey_dashboard.control_center_state import build_control_center_state
from dopey_dashboard.chart_state import build_chart_state
from dopey_dashboard.desktop_tray import (
    DesktopTrayController,
    notification_source_summary,
    resolve_notification_state_path,
    resolve_tray_icon_path,
)
from dopey_dashboard.scheduler_control import SchedulerControlError, set_research_core_enabled
from dopey_live.control import (
    CONTROL_CONFIRMATION as LIVE_BRANCH_CONTROL_CONFIRMATION,
    LiveBranchControlError,
    set_options_execution_enabled,
)
from dopey_symbol_lab.lab import build_symbol_lab_state


APP_TITLE = "DOPEY Control Center"
EXPECTED_PYWEBVIEW_VERSION = "6.2.1"
EXPECTED_PYSTRAY_VERSION = "0.19.5"
NOTIFICATION_POLL_INTERVAL_SECONDS = 15.0
WINDOW_HEIGHT = 960
WINDOW_WIDTH = 1540
WINDOW_MINIMUM_HEIGHT = 720
WINDOW_MINIMUM_WIDTH = 1024
WINDOW_BACKGROUND = "#090B0D"
DESKTOP_API_METHODS: Final[tuple[str, ...]] = (
    "close_window",
    "get_chart",
    "get_chart_coach",
    "get_state",
    "get_symbol_lab",
    "minimize_window",
    "set_instrument_mode",
    "set_llm_provider",
    "set_openrouter_api_key",
    "set_options_execution",
    "set_research_core",
    "toggle_maximize_window",
)
PROVIDER_CONTROL_CONFIRMATION = "paper_research_configuration"
HEAD_COACH_TIMEOUT_SECONDS = 300


class DesktopHostError(RuntimeError):
    """Raised when the native host cannot satisfy its local-only contract."""


class NativeWindow(Protocol):
    """Window operations used by the connector."""

    def minimize(self) -> None:
        """Minimize the native window."""

    def maximize(self) -> None:
        """Maximize the native window."""

    def hide(self) -> None:
        """Hide the native window while the tray remains active."""

    def restore(self) -> None:
        """Restore the native window."""

    def show(self) -> None:
        """Show the native window."""

    def destroy(self) -> None:
        """Close the native window."""

    def get_current_url(self) -> str | None:
        """Return the renderer's current URL."""


def _looks_like_repo_root(candidate: Path) -> bool:
    return (
        candidate.is_dir()
        and (candidate / "pyproject.toml").is_file()
        and (candidate / "dopey").is_dir()
        and (candidate / "dopey_dashboard").is_dir()
    )


def _unique_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        resolved = path.expanduser().resolve()
        key = os.path.normcase(str(resolved))
        if key not in seen:
            seen.add(key)
            unique.append(resolved)
    return tuple(unique)


def resolve_repo_root() -> Path:
    """Resolve the checked-out DOPEY root or fail with every checked path."""

    environment_value = os.environ.get("DOPEY_REPO_ROOT", "").strip()
    if environment_value:
        environment_candidate = Path(environment_value).expanduser().resolve()
        if _looks_like_repo_root(environment_candidate):
            return environment_candidate
        raise DesktopHostError(
            "DOPEY_REPO_ROOT does not identify a DOPEY checkout: "
            f"path={environment_candidate}"
        )
    development_candidate = Path(__file__).resolve().parents[1]
    home_candidate = Path.home() / "dopey"
    candidates = _unique_paths((development_candidate, home_candidate))
    for candidate in candidates:
        if _looks_like_repo_root(candidate):
            return candidate
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise DesktopHostError(
        "Unable to resolve the DOPEY repository root. Set DOPEY_REPO_ROOT to "
        f"the checkout directory. Checked: {checked}"
    )


def resolve_frontend_index(repo_root: Path) -> Path:
    """Resolve only the compiled local dashboard entrypoint."""

    bundle_root_value = getattr(sys, "_MEIPASS", "")
    if bundle_root_value:
        candidates = _unique_paths(
            (Path(str(bundle_root_value)) / "desktop" / "dist" / "index.html",)
        )
    else:
        candidates = _unique_paths((repo_root / "desktop" / "dist" / "index.html",))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise DesktopHostError(
        "The compiled desktop dashboard is missing. Run desktop\\build_desktop.ps1. "
        f"Checked: {checked}"
    )


def _require_mapping(value: object, operation: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise DesktopHostError(
            f"{operation} returned {type(value).__name__}; expected dict[str, object]"
        )
    if not all(isinstance(key, str) for key in value):
        raise DesktopHostError(f"{operation} returned a mapping with non-string keys")
    return value


def _execution_seal_verified(state: dict[str, object]) -> bool:
    constitution = state.get("constitution")
    if not isinstance(constitution, dict):
        return False
    return (
        constitution.get("execution_seal_state") == "SEALED"
        and state.get("research_branch_paper_only") is True
    )


def _require_provider_confirmation(confirmation: str) -> None:
    if confirmation != PROVIDER_CONTROL_CONFIRMATION:
        raise DesktopHostError(
            "LLM provider control requires confirmation='paper_research_configuration'"
        )


def _enforce_local_navigation(window: NativeWindow, expected_url: str) -> None:
    current_url = window.get_current_url()
    if current_url is None:
        window.destroy()
        raise DesktopHostError("Renderer navigation could not be verified")
    normalized_current = current_url.split("#", maxsplit=1)[0].split("?", maxsplit=1)[0]
    normalized_expected = expected_url.split("#", maxsplit=1)[0].split("?", maxsplit=1)[0]
    if normalized_current.casefold() != normalized_expected.casefold():
        window.destroy()
        raise DesktopHostError(
            "Blocked renderer navigation outside the compiled local control surface: "
            f"expected={normalized_expected}, actual={normalized_current}"
        )


class DesktopApi:
    """The complete and intentionally narrow Python surface exposed to JavaScript."""

    def __init__(self, repo_root: Path, frontend_url: str) -> None:
        self._repo_root = repo_root
        self._frontend_url = frontend_url
        self._window: NativeWindow | None = None
        self._window_is_maximized = False
        self._state_lock = RLock()
        self._coach_lock = RLock()
        self._window_lock = RLock()

    def _bind_window(self, window: NativeWindow) -> None:
        with self._window_lock:
            if self._window is not None:
                raise DesktopHostError(
                    "The desktop connector is already bound to a window"
                )
            self._window = window

    def _require_window(self) -> NativeWindow:
        if self._window is None:
            raise DesktopHostError("The native window is not ready")
        return self._window

    def _require_local_renderer(self) -> None:
        with self._window_lock:
            _enforce_local_navigation(self._require_window(), self._frontend_url)

    def get_state(self) -> dict[str, object]:
        """Return a fresh, read-only operator snapshot."""

        self._require_local_renderer()
        with self._state_lock:
            try:
                state = build_control_center_state(self._repo_root)
            except (OSError, TypeError, ValueError, SchedulerControlError) as error:
                raise DesktopHostError(
                    f"Unable to build control-center state for {self._repo_root}: {error}"
                ) from error
            return _require_mapping(state, "build_control_center_state")

    def get_chart(self, symbol: str, timeframe: str) -> dict[str, object]:
        """Return bounded, read-only candlestick and technical evidence."""

        if not isinstance(symbol, str):
            raise TypeError(f"symbol must be a str, received {type(symbol).__name__}")
        if not isinstance(timeframe, str):
            raise TypeError(
                f"timeframe must be a str, received {type(timeframe).__name__}"
            )
        self._require_local_renderer()
        with self._state_lock:
            try:
                state = build_chart_state(self._repo_root, symbol, timeframe)
            except (OSError, TypeError, ValueError) as error:
                raise DesktopHostError(
                    "Unable to build chart intelligence: "
                    f"symbol={symbol!r}, timeframe={timeframe!r}, error={error}"
                ) from error
            return _require_mapping(state, "build_chart_state")

    def get_chart_coach(
        self,
        symbol: str,
        timeframe: str,
        head_coach_id: str,
    ) -> dict[str, object]:
        """Run an explicit paper-only Evidence Coach plus Claude or Codex head coach."""

        if not isinstance(symbol, str):
            raise TypeError(f"symbol must be a str, received {type(symbol).__name__}")
        if not isinstance(timeframe, str):
            raise TypeError(
                f"timeframe must be a str, received {type(timeframe).__name__}"
            )
        if not isinstance(head_coach_id, str):
            raise TypeError(
                "head_coach_id must be a str, "
                f"received {type(head_coach_id).__name__}"
            )
        self._require_local_renderer()
        with self._coach_lock:
            try:
                state = run_two_coach_review(
                    self._repo_root,
                    symbol,
                    timeframe,
                    head_coach_id,
                    HEAD_COACH_TIMEOUT_SECONDS,
                )
            except (OSError, TypeError, ValueError, TwoCoachContractError) as error:
                raise DesktopHostError(
                    "Unable to complete the two-coach chart review: "
                    f"symbol={symbol!r}, timeframe={timeframe!r}, "
                    f"head_coach_id={head_coach_id!r}, error={error}"
                ) from error
            return _require_mapping(state, "run_two_coach_review")

    def get_symbol_lab(
        self,
        symbol: str,
        strategy_mode: str,
        scenario_stock_price: float | None,
        days_forward: int,
        iv_shift: float,
    ) -> dict[str, object]:
        """Return one interactive, paper-only symbol and option research dossier."""

        if not isinstance(symbol, str):
            raise TypeError(f"symbol must be a str, received {type(symbol).__name__}")
        if not isinstance(strategy_mode, str):
            raise TypeError(
                "strategy_mode must be a str, "
                f"received {type(strategy_mode).__name__}"
            )
        if scenario_stock_price is not None and (
            isinstance(scenario_stock_price, bool)
            or not isinstance(scenario_stock_price, (int, float))
        ):
            raise TypeError(
                "scenario_stock_price must be numeric or null, "
                f"received {type(scenario_stock_price).__name__}"
            )
        if isinstance(days_forward, bool) or not isinstance(days_forward, int):
            raise TypeError(
                f"days_forward must be an int, received {type(days_forward).__name__}"
            )
        if isinstance(iv_shift, bool) or not isinstance(iv_shift, (int, float)):
            raise TypeError(
                f"iv_shift must be numeric, received {type(iv_shift).__name__}"
            )
        self._require_local_renderer()
        with self._state_lock:
            try:
                state = build_symbol_lab_state(
                    self._repo_root,
                    symbol,
                    strategy_mode,
                    None if scenario_stock_price is None else float(scenario_stock_price),
                    days_forward,
                    float(iv_shift),
                )
            except (FileNotFoundError, OSError, TypeError, ValueError) as error:
                raise DesktopHostError(
                    "Unable to build symbol intelligence lab: "
                    f"symbol={symbol!r}, strategy_mode={strategy_mode!r}, "
                    f"scenario_stock_price={scenario_stock_price!r}, "
                    f"days_forward={days_forward}, iv_shift={iv_shift}, error={error}"
                ) from error
            return _require_mapping(state, "build_symbol_lab_state")

    def set_research_core(self, enabled: bool, confirmation: str) -> dict[str, object]:
        """Request a confirmed paper-research scheduler state transition."""

        if type(enabled) is not bool:
            raise TypeError(
                f"enabled must be a bool, received {type(enabled).__name__}"
            )
        if not isinstance(confirmation, str):
            raise TypeError(
                f"confirmation must be a str, received {type(confirmation).__name__}"
            )
        self._require_local_renderer()
        with self._state_lock:
            try:
                boundary_state = build_control_center_state(self._repo_root)
                if not _execution_seal_verified(boundary_state):
                    raise DesktopHostError(
                        "Paper-automation control is blocked because the execution seal is not verified"
                    )
                state = set_research_core_enabled(
                    self._repo_root,
                    enabled,
                    confirmation,
                )
            except (OSError, TypeError, ValueError, SchedulerControlError, DesktopHostError) as error:
                raise DesktopHostError(
                    "Unable to change the paper-research scheduler state: "
                    f"enabled={enabled}, error={error}"
                ) from error
            return _require_mapping(state, "set_research_core_enabled")

    def set_llm_provider(
        self,
        provider: str,
        enabled: bool,
        confirmation: str,
    ) -> dict[str, object]:
        """Set one analysis-only LLM provider route."""

        if not isinstance(provider, str):
            raise TypeError(f"provider must be a str, received {type(provider).__name__}")
        if type(enabled) is not bool:
            raise TypeError(f"enabled must be a bool, received {type(enabled).__name__}")
        if not isinstance(confirmation, str):
            raise TypeError(
                f"confirmation must be a str, received {type(confirmation).__name__}"
            )
        self._require_local_renderer()
        with self._state_lock:
            try:
                _require_provider_confirmation(confirmation)
                boundary_state = build_control_center_state(self._repo_root)
                if not _execution_seal_verified(boundary_state):
                    raise DesktopHostError(
                        "LLM provider control is blocked because the execution seal is not verified"
                    )
                set_provider_enabled(provider, enabled)
                return _require_mapping(provider_control_state(), "provider_control_state")
            except (OSError, TypeError, ValueError, ProviderControlError, DesktopHostError) as error:
                raise DesktopHostError(
                    "Unable to change the analysis-only LLM provider state: "
                    f"provider={provider!r}, enabled={enabled}, error={error}"
                ) from error

    def set_instrument_mode(self, instrument_mode: str, confirmation: str) -> dict[str, object]:
        """Set the stock/options focus for future paper research."""

        if not isinstance(instrument_mode, str):
            raise TypeError(
                f"instrument_mode must be a str, received {type(instrument_mode).__name__}"
            )
        if not isinstance(confirmation, str):
            raise TypeError(
                f"confirmation must be a str, received {type(confirmation).__name__}"
            )
        self._require_local_renderer()
        with self._state_lock:
            try:
                _require_provider_confirmation(confirmation)
                boundary_state = build_control_center_state(self._repo_root)
                if not _execution_seal_verified(boundary_state):
                    raise DesktopHostError(
                        "Instrument routing control is blocked because the execution seal is not verified"
                    )
                set_provider_instrument_mode(instrument_mode)
                return _require_mapping(provider_control_state(), "provider_control_state")
            except (OSError, TypeError, ValueError, ProviderControlError, DesktopHostError) as error:
                raise DesktopHostError(
                    "Unable to change the paper-research instrument mode: "
                    f"instrument_mode={instrument_mode!r}, error={error}"
                ) from error

    def set_openrouter_api_key(self, api_key: str, confirmation: str) -> dict[str, object]:
        """Write an OpenRouter key into Windows user-scoped encrypted storage."""

        if not isinstance(api_key, str):
            raise TypeError(f"api_key must be a str, received {type(api_key).__name__}")
        if not isinstance(confirmation, str):
            raise TypeError(
                f"confirmation must be a str, received {type(confirmation).__name__}"
            )
        self._require_local_renderer()
        with self._state_lock:
            try:
                _require_provider_confirmation(confirmation)
                boundary_state = build_control_center_state(self._repo_root)
                if not _execution_seal_verified(boundary_state):
                    raise DesktopHostError(
                        "OpenRouter key storage is blocked because the execution seal is not verified"
                    )
                store_openrouter_api_key(api_key)
                return _require_mapping(provider_control_state(), "provider_control_state")
            except (OSError, TypeError, ValueError, ProviderControlError, DesktopHostError) as error:
                raise DesktopHostError(
                    f"Unable to store the OpenRouter API key in Windows user scope: error={error}"
                ) from error

    def set_options_execution(self, enabled: bool, confirmation: str) -> dict[str, object]:
        """Set the user-scoped live options gate; stock execution is unaffected."""

        if type(enabled) is not bool:
            raise TypeError(f"enabled must be a bool, received {type(enabled).__name__}")
        if not isinstance(confirmation, str):
            raise TypeError(
                f"confirmation must be a str, received {type(confirmation).__name__}"
            )
        if confirmation != LIVE_BRANCH_CONTROL_CONFIRMATION:
            raise DesktopHostError(
                f"Live options control requires confirmation={LIVE_BRANCH_CONTROL_CONFIRMATION!r}"
            )
        self._require_local_renderer()
        with self._state_lock:
            try:
                set_options_execution_enabled(enabled, confirmation)
                return _require_mapping(
                    build_control_center_state(self._repo_root).get("live_branch"),
                    "set_options_execution_enabled",
                )
            except (OSError, TypeError, ValueError, LiveBranchControlError) as error:
                raise DesktopHostError(
                    f"Unable to change the Live Branch options gate: enabled={enabled}, error={error}"
                ) from error

    def minimize_window(self) -> dict[str, str]:
        """Minimize the native window."""

        with self._window_lock:
            _enforce_local_navigation(self._require_window(), self._frontend_url)
            self._require_window().minimize()
            return {"status": "ok", "window": "minimized"}

    def toggle_maximize_window(self) -> dict[str, str]:
        """Toggle the native window between restored and maximized states."""

        with self._window_lock:
            window = self._require_window()
            _enforce_local_navigation(window, self._frontend_url)
            if self._window_is_maximized:
                window.restore()
                self._window_is_maximized = False
                return {"status": "ok", "window": "restored"}
            window.maximize()
            self._window_is_maximized = True
            return {"status": "ok", "window": "maximized"}

    def close_window(self) -> dict[str, str]:
        """Hide the native window while the tray and notifications stay active."""

        with self._window_lock:
            _enforce_local_navigation(self._require_window(), self._frontend_url)
            self._require_window().hide()
            return {"status": "ok", "window": "hidden_to_tray"}


def smoke_check(repo_root: Path, frontend_index: Path) -> dict[str, object]:
    """Validate packaging, frontend, and read-only backend integration."""

    installed_version = importlib.metadata.version("pywebview")
    if installed_version != EXPECTED_PYWEBVIEW_VERSION:
        raise DesktopHostError(
            "Unexpected pywebview version: "
            f"installed={installed_version}, required={EXPECTED_PYWEBVIEW_VERSION}"
        )
    installed_pystray_version = importlib.metadata.version("pystray")
    if installed_pystray_version != EXPECTED_PYSTRAY_VERSION:
        raise DesktopHostError(
            "Unexpected pystray version: "
            f"installed={installed_pystray_version}, required={EXPECTED_PYSTRAY_VERSION}"
        )
    state = _require_mapping(
        build_control_center_state(repo_root),
        "build_control_center_state",
    )
    try:
        json.dumps(state, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise DesktopHostError(
            f"Control-center state is not strict JSON: {error}"
        ) from error
    tray_summary = notification_source_summary(repo_root)
    paper_only = state.get("paper_only")
    live_blocked = state.get("live_blocked")
    return {
        "status": "pass",
        "app": APP_TITLE,
        "renderer": "edgechromium",
        "server_started": False,
        "repo_root": str(repo_root),
        "frontend_index": str(frontend_index),
        "pywebview_version": installed_version,
        "pystray_version": installed_pystray_version,
        "system_tray": tray_summary,
        "desktop_api_methods": list(DESKTOP_API_METHODS),
        "live_execution_enabled": True,
        "paper_only": paper_only if isinstance(paper_only, bool) else None,
        "live_blocked": live_blocked if isinstance(live_blocked, bool) else None,
        "backend_state_keys": sorted(state),
    }


def launch(repo_root: Path, frontend_index: Path) -> None:
    """Launch the frameless EdgeChromium desktop shell."""

    frontend_url = frontend_index.as_uri()
    connector = DesktopApi(repo_root, frontend_url)
    window = webview.create_window(
        APP_TITLE,
        frontend_url,
        js_api=connector,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        resizable=True,
        min_size=(WINDOW_MINIMUM_WIDTH, WINDOW_MINIMUM_HEIGHT),
        frameless=True,
        easy_drag=False,
        shadow=True,
        confirm_close=False,
        background_color=WINDOW_BACKGROUND,
        text_select=True,
        zoomable=True,
        draggable=False,
    )
    if window is None:
        raise DesktopHostError("pywebview did not create the native window")
    connector._bind_window(window)
    window.events.loaded += lambda: _enforce_local_navigation(window, frontend_url)
    tray = DesktopTrayController(
        repo_root,
        resolve_notification_state_path(),
        resolve_tray_icon_path(repo_root),
        window,
        NOTIFICATION_POLL_INTERVAL_SECONDS,
    )
    tray.start()
    try:
        webview.start(
            gui="edgechromium",
            debug=False,
            http_server=False,
            private_mode=True,
        )
    finally:
        tray.stop()


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the DOPEY Control Center")
    parser.add_argument(
        "--smoke-check",
        action="store_true",
        help="validate the local desktop integration without opening a window",
    )
    return parser.parse_args(arguments)


def main(arguments: list[str]) -> int:
    parsed = parse_arguments(arguments)
    repo_root = resolve_repo_root()
    frontend_index = resolve_frontend_index(repo_root)
    if parsed.smoke_check:
        print(
            json.dumps(smoke_check(repo_root, frontend_index), indent=2, sort_keys=True)
        )
        return 0
    launch(repo_root, frontend_index)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
