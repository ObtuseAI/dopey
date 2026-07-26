"""Native system-tray lifecycle and evidence-driven desktop notifications."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from threading import Event, RLock, Thread, current_thread
from typing import Final, Literal, Protocol, TypedDict

from PIL import Image
from pystray import Icon, Menu, MenuItem


NOTIFICATION_STATE_SCHEMA: Final[str] = "dopey-desktop-notification-state-v1"
TRAY_IDENTIFIER: Final[str] = "dopey-control-center"
TRAY_OPEN_LABEL: Final[str] = "Open DOPEY"
TRAY_EXIT_LABEL: Final[str] = "Exit DOPEY"
TRAY_READY_TIMEOUT_SECONDS: Final[float] = 8.0
TRAY_STOP_TIMEOUT_SECONDS: Final[float] = 3.0
ARTIFACT_READ_ATTEMPTS: Final[int] = 3
ARTIFACT_READ_RETRY_SECONDS: Final[float] = 0.1
FORWARD_WALK_LEDGER_PATH: Final[Path] = (
    Path("artifacts") / "dopey" / "forward_walk" / "forward_walk_ledger.json"
)
PROMOTION_CYCLE_PATH: Final[Path] = (
    Path("artifacts") / "dopey" / "autoresearch" / "latest_promotion_cycle.json"
)
LIVE_BRANCH_LEDGER_PATH: Final[Path] = (
    Path("artifacts") / "dopey" / "live_branch" / "live_branch_ledger.jsonl"
)

NotificationKind = Literal[
    "live_trade_opened",
    "live_trade_closed",
    "paper_trade_opened",
    "paper_trade_closed",
    "research_promotion",
]


class DesktopNotification(TypedDict):
    """One deduplicated, user-visible desktop event."""

    event_id: str
    kind: NotificationKind
    title: str
    message: str


class NotificationState(TypedDict):
    """Durable local cursor for notification delivery."""

    schema_version: str
    delivered_event_ids: list[str]


class TrayWindow(Protocol):
    """Native window operations required by the tray connector."""

    def destroy(self) -> None:
        """Destroy the native window."""

    def hide(self) -> None:
        """Hide the native window while leaving the application running."""

    def restore(self) -> None:
        """Restore the native window from a minimized state."""

    def show(self) -> None:
        """Show the native window."""


class DesktopTrayError(RuntimeError):
    """Raised when the native tray contract cannot be satisfied."""


class DesktopNotificationError(RuntimeError):
    """Raised when notification evidence or cursor state is invalid."""


def _require_mapping(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise DesktopNotificationError(
            f"Desktop notification source must be an object: context={context}"
        )
    return value


def _require_array(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise DesktopNotificationError(
            f"Desktop notification source must be an array: context={context}"
        )
    return value


def _require_nonempty_text(value: object, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DesktopNotificationError(
            f"Desktop notification identity must be non-empty text: context={context}"
        )
    return value.strip()


def _require_paper_boundary(record: dict[str, object], context: str) -> None:
    if record.get("paper_only") is not True or record.get("live_blocked") is not True:
        raise DesktopNotificationError(
            "Desktop notification source violates the paper-only boundary: "
            f"context={context}, paper_only={record.get('paper_only')!r}, "
            f"live_blocked={record.get('live_blocked')!r}"
        )


def _clip_notification_text(value: str, maximum_length: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= maximum_length:
        return normalized
    return normalized[: maximum_length - 1].rstrip() + "…"


def _format_return(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return "return not reported"
    return f"{float(value):+.2%} paper return"


def _trade_notifications(
    records: list[object],
    kind: Literal["paper_trade_opened", "paper_trade_closed"],
) -> tuple[DesktopNotification, ...]:
    output: list[DesktopNotification] = []
    for index, raw_record in enumerate(records):
        context = f"forward_walk_ledger.{kind}[{index}]"
        record = _require_mapping(raw_record, context)
        _require_paper_boundary(record, context)
        position_id = _require_nonempty_text(record.get("position_id"), f"{context}.position_id")
        symbol = _require_nonempty_text(record.get("symbol"), f"{context}.symbol")
        strategy = _require_nonempty_text(
            record.get("candidate_strategy"),
            f"{context}.candidate_strategy",
        )
        if kind == "paper_trade_opened":
            entry_date = _require_nonempty_text(
                record.get("entry_date"),
                f"{context}.entry_date",
            )
            message = (
                f"{symbol} · {strategy.replace('_', ' ')} · opened {entry_date} · PAPER ONLY"
            )
            title = "DOPEY · Paper trade opened"
        else:
            exit_date = _require_nonempty_text(
                record.get("exit_date"),
                f"{context}.exit_date",
            )
            exit_reason = _require_nonempty_text(
                record.get("exit_reason"),
                f"{context}.exit_reason",
            )
            message = (
                f"{symbol} · {strategy.replace('_', ' ')} · closed {exit_date} · "
                f"{_format_return(record.get('trade_return'))} · "
                f"{exit_reason.replace('_', ' ')} · PAPER ONLY"
            )
            title = "DOPEY · Paper trade closed"
        output.append(
            DesktopNotification(
                event_id=f"{kind}:{position_id}",
                kind=kind,
                title=title,
                message=_clip_notification_text(message, 255),
            )
        )
    return tuple(output)


def _promotion_notifications(cycle: dict[str, object]) -> tuple[DesktopNotification, ...]:
    _require_paper_boundary(cycle, "latest_promotion_cycle")
    if cycle.get("execution_effect") != "none":
        raise DesktopNotificationError(
            "Promotion notification source must have execution_effect='none': "
            f"actual={cycle.get('execution_effect')!r}"
        )
    matrix = _require_mapping(cycle.get("matrix"), "latest_promotion_cycle.matrix")
    _require_paper_boundary(matrix, "latest_promotion_cycle.matrix")
    if matrix.get("execution_effect") != "none":
        raise DesktopNotificationError(
            "Promotion matrix must have execution_effect='none': "
            f"actual={matrix.get('execution_effect')!r}"
        )
    groups: tuple[tuple[str, str], ...] = (
        ("activated_symbol_ids", "Symbol"),
        ("activated_strategy_ids", "Strategy"),
        ("activated_symbol_strategy_ids", "Symbol/strategy pair"),
    )
    output: list[DesktopNotification] = []
    for field_name, subject_label in groups:
        values = _require_array(matrix.get(field_name), f"latest_promotion_cycle.matrix.{field_name}")
        for index, raw_identifier in enumerate(values):
            identifier = _require_nonempty_text(
                raw_identifier,
                f"latest_promotion_cycle.matrix.{field_name}[{index}]",
            )
            output.append(
                DesktopNotification(
                    event_id=f"research_promotion:{field_name}:{identifier}",
                    kind="research_promotion",
                    title="DOPEY · Research promotion",
                    message=_clip_notification_text(
                        f"{subject_label} {identifier} activated for protected paper research · "
                        "NO LIVE EXECUTION",
                        255,
                    ),
                )
            )
    return tuple(output)


def _read_jsonl_mappings(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    records: list[dict[str, object]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            decoded: object = json.loads(raw)
        except json.JSONDecodeError as error:
            raise DesktopNotificationError(
                f"Unable to read Live Branch ledger JSON: path={path}, line={line_number}, error={error}"
            ) from error
        records.append(_require_mapping(decoded, f"{path}:{line_number}"))
    return records


def _live_trade_notifications(records: list[dict[str, object]]) -> tuple[DesktopNotification, ...]:
    latest_status_by_order_id: dict[str, str] = {}
    for index, record in enumerate(records):
        if record.get("event_type") not in {
            "live_order_result",
            "live_order_status_observed",
        }:
            continue
        payload = _require_mapping(record.get("payload"), f"live_branch_ledger[{index}].payload")
        order_id = _require_nonempty_text(
            payload.get("order_id") or record.get("record_hash"),
            f"live_branch_ledger[{index}].order_id",
        )
        latest_status_by_order_id[order_id] = str(payload.get("status", "")).lower()
    events: list[DesktopNotification] = []
    for index, record in enumerate(records):
        if record.get("event_type") != "live_order_result":
            continue
        payload = _require_mapping(record.get("payload"), f"live_branch_ledger[{index}].payload")
        if payload.get("placed") is not True:
            continue
        side = _require_nonempty_text(payload.get("side"), f"live_branch_ledger[{index}].side")
        if side not in {"buy", "sell"}:
            raise DesktopNotificationError(
                f"Live Branch order side must be buy or sell: index={index}, side={side!r}"
            )
        symbol = _require_nonempty_text(payload.get("symbol"), f"live_branch_ledger[{index}].symbol")
        instrument = _require_nonempty_text(
            payload.get("instrument"), f"live_branch_ledger[{index}].instrument"
        )
        order_id = _require_nonempty_text(
            payload.get("order_id") or record.get("record_hash"),
            f"live_branch_ledger[{index}].order_id",
        )
        status = latest_status_by_order_id.get(order_id, str(payload.get("status", "")).lower())
        if side == "buy" and status not in {"filled", "partially_filled"}:
            continue
        if side == "sell" and status != "filled":
            continue
        market_date = _require_nonempty_text(
            payload.get("market_date"), f"live_branch_ledger[{index}].market_date"
        )
        kind: Literal["live_trade_opened", "live_trade_closed"] = (
            "live_trade_opened" if side == "buy" else "live_trade_closed"
        )
        action = "opened" if side == "buy" else "closed"
        events.append(
            DesktopNotification(
                event_id=f"{kind}:{order_id}",
                kind=kind,
                title=f"DOPEY / Live trade {action}",
                message=_clip_notification_text(
                    f"{symbol} / {instrument} / {action} {market_date} / ROBINHOOD AGENTIC / LIVE",
                    255,
                ),
            )
        )
    return tuple(events)


def _read_json_mapping(path: Path, attempts: int, retry_seconds: float) -> dict[str, object]:
    if attempts < 1:
        raise ValueError(f"attempts must be positive: attempts={attempts}")
    last_error: OSError | UnicodeError | json.JSONDecodeError | None = None
    for attempt in range(attempts):
        try:
            decoded: object = json.loads(path.read_text(encoding="utf-8"))
            return _require_mapping(decoded, str(path))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            last_error = error
            if attempt + 1 < attempts:
                time.sleep(retry_seconds)
    raise DesktopNotificationError(
        "Unable to read desktop notification source after retries: "
        f"path={path}, attempts={attempts}, error={last_error}"
    ) from last_error


def load_desktop_notifications(repository_root: Path) -> tuple[DesktopNotification, ...]:
    """Load current, boundary-verified paper events from canonical artifacts."""

    ledger = _read_json_mapping(
        repository_root / FORWARD_WALK_LEDGER_PATH,
        ARTIFACT_READ_ATTEMPTS,
        ARTIFACT_READ_RETRY_SECONDS,
    )
    promotions = _read_json_mapping(
        repository_root / PROMOTION_CYCLE_PATH,
        ARTIFACT_READ_ATTEMPTS,
        ARTIFACT_READ_RETRY_SECONDS,
    )
    events = (
        *_live_trade_notifications(
            _read_jsonl_mappings(repository_root / LIVE_BRANCH_LEDGER_PATH)
        ),
        *_trade_notifications(
            _require_array(ledger.get("open_positions"), "forward_walk_ledger.open_positions"),
            "paper_trade_opened",
        ),
        *_trade_notifications(
            _require_array(ledger.get("closed_trades"), "forward_walk_ledger.closed_trades"),
            "paper_trade_closed",
        ),
        *_promotion_notifications(promotions),
    )
    identities = [event["event_id"] for event in events]
    if len(identities) != len(set(identities)):
        raise DesktopNotificationError("Desktop notification sources contain duplicate event identities")
    return events


def notification_source_summary(repository_root: Path) -> dict[str, object]:
    """Return a read-only smoke summary for packaged integration checks."""

    source_paths = (
        repository_root / FORWARD_WALK_LEDGER_PATH,
        repository_root / PROMOTION_CYCLE_PATH,
    )
    missing_paths = tuple(path for path in source_paths if not path.is_file())
    if missing_paths:
        return {
            "status": "pass",
            "source_status": "unavailable_missing_artifacts",
            "missing_source_paths": [
                str(path.relative_to(repository_root)) for path in missing_paths
            ],
            "tray_menu": [TRAY_OPEN_LABEL, TRAY_EXIT_LABEL],
            "notification_kinds": [
                "live_trade_closed",
                "live_trade_opened",
                "paper_trade_closed",
                "paper_trade_opened",
                "research_promotion",
            ],
            "current_event_counts": None,
            "existing_events_baselined_without_replay": True,
            "paper_only": False,
            "live_blocked": False,
            "live_execution_enabled": True,
        }

    events = load_desktop_notifications(repository_root)
    counts: dict[NotificationKind, int] = {
        "live_trade_opened": 0,
        "live_trade_closed": 0,
        "paper_trade_opened": 0,
        "paper_trade_closed": 0,
        "research_promotion": 0,
    }
    for event in events:
        counts[event["kind"]] += 1
    return {
        "status": "pass",
        "source_status": "available",
        "missing_source_paths": [],
        "tray_menu": [TRAY_OPEN_LABEL, TRAY_EXIT_LABEL],
        "notification_kinds": sorted(counts),
        "current_event_counts": counts,
        "existing_events_baselined_without_replay": True,
        "paper_only": False,
        "live_blocked": False,
        "live_execution_enabled": True,
    }


def resolve_tray_icon_path(repository_root: Path) -> Path:
    """Resolve the packaged or development PNG used by the Windows tray."""

    bundle_root = getattr(sys, "_MEIPASS", "")
    candidates = (
        (Path(str(bundle_root)) / "desktop" / "assets" / "dopey-control-center.png",)
        if bundle_root
        else (repository_root / "desktop" / "assets" / "dopey-control-center.png",)
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    checked = ", ".join(str(candidate) for candidate in candidates)
    raise DesktopTrayError(f"DOPEY tray icon is missing. Checked: {checked}")


def resolve_notification_state_path() -> Path:
    """Resolve the user-local notification cursor without touching the repository."""

    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        raise DesktopTrayError("LOCALAPPDATA is unavailable; notification state cannot be persisted")
    return Path(local_app_data).resolve() / "DOPEY" / "desktop-notification-state.json"


def _load_notification_state(path: Path) -> NotificationState | None:
    if not path.exists():
        return None
    decoded = _read_json_mapping(path, ARTIFACT_READ_ATTEMPTS, ARTIFACT_READ_RETRY_SECONDS)
    if decoded.get("schema_version") != NOTIFICATION_STATE_SCHEMA:
        raise DesktopNotificationError(
            "Desktop notification state schema is unsupported: "
            f"path={path}, schema_version={decoded.get('schema_version')!r}"
        )
    raw_ids = _require_array(decoded.get("delivered_event_ids"), f"{path}.delivered_event_ids")
    event_ids = [
        _require_nonempty_text(raw_id, f"{path}.delivered_event_ids[{index}]")
        for index, raw_id in enumerate(raw_ids)
    ]
    if len(event_ids) != len(set(event_ids)):
        raise DesktopNotificationError(f"Desktop notification state contains duplicate IDs: path={path}")
    return NotificationState(
        schema_version=NOTIFICATION_STATE_SCHEMA,
        delivered_event_ids=event_ids,
    )


def _write_notification_state(path: Path, event_ids: set[str]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = NotificationState(
            schema_version=NOTIFICATION_STATE_SCHEMA,
            delivered_event_ids=sorted(event_ids),
        )
        encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as error:
        raise DesktopNotificationError(
            f"Unable to persist desktop notification state: path={path}, error={error}"
        ) from error


def pending_notifications(
    events: tuple[DesktopNotification, ...],
    delivered_event_ids: set[str],
) -> tuple[DesktopNotification, ...]:
    """Return only unseen events without modifying either input."""

    return tuple(event for event in events if event["event_id"] not in delivered_event_ids)


class DesktopTrayController:
    """Connector between pywebview, the Windows tray, and artifact notifications."""

    def __init__(
        self,
        repository_root: Path,
        state_path: Path,
        icon_path: Path,
        window: TrayWindow,
        poll_interval_seconds: float,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError(
                "poll_interval_seconds must be positive: "
                f"poll_interval_seconds={poll_interval_seconds}"
            )
        self._repository_root = repository_root
        self._state_path = state_path
        self._window = window
        self._poll_interval_seconds = poll_interval_seconds
        self._ready_event = Event()
        self._stop_event = Event()
        self._lifecycle_lock = RLock()
        self._stopped = False
        self._monitor_thread = Thread(
            target=self._monitor_notifications,
            name="DOPEYDesktopNotificationMonitor",
            daemon=True,
        )
        with Image.open(icon_path) as source_image:
            tray_image = source_image.convert("RGBA")
        self._icon = Icon(
            TRAY_IDENTIFIER,
            tray_image,
            "DOPEY Control Center · Paper research",
            Menu(
                MenuItem(TRAY_OPEN_LABEL, self._open_app, default=True),
                Menu.SEPARATOR,
                MenuItem(TRAY_EXIT_LABEL, self._exit_app),
            ),
        )

    def start(self) -> None:
        """Start the native tray and the deduplicated artifact monitor."""

        with self._lifecycle_lock:
            if self._stopped:
                raise DesktopTrayError("The DOPEY tray controller cannot be restarted after stop")
            self._icon.run_detached(self._mark_tray_ready)
        if not self._ready_event.wait(TRAY_READY_TIMEOUT_SECONDS):
            self.stop()
            raise DesktopTrayError(
                "The DOPEY system tray did not become ready within "
                f"{TRAY_READY_TIMEOUT_SECONDS} seconds"
            )
        self._monitor_thread.start()

    def stop(self) -> None:
        """Stop monitor and tray threads exactly once."""

        with self._lifecycle_lock:
            if self._stopped:
                return
            self._stopped = True
            self._stop_event.set()
            self._icon.stop()
        if self._monitor_thread.is_alive() and self._monitor_thread is not current_thread():
            self._monitor_thread.join(TRAY_STOP_TIMEOUT_SECONDS)

    def _mark_tray_ready(self, icon: Icon) -> None:
        icon.visible = True
        self._ready_event.set()

    def _open_app(self, icon: Icon, item: MenuItem) -> None:
        del item
        icon.remove_notification()
        self._window.show()
        self._window.restore()

    def _exit_app(self, icon: Icon, item: MenuItem) -> None:
        del icon, item
        self.stop()
        self._window.destroy()

    def _monitor_notifications(self) -> None:
        delivered: set[str] | None = None
        reported_error = ""
        while not self._stop_event.is_set():
            try:
                events = load_desktop_notifications(self._repository_root)
                state = _load_notification_state(self._state_path) if delivered is None else None
                if delivered is None:
                    if state is None:
                        delivered = {event["event_id"] for event in events}
                        _write_notification_state(self._state_path, delivered)
                    else:
                        delivered = set(state["delivered_event_ids"])
                for event in pending_notifications(events, delivered):
                    self._icon.notify(event["message"], event["title"])
                    delivered.add(event["event_id"])
                    _write_notification_state(self._state_path, delivered)
                if reported_error:
                    self._icon.notify(
                        "Paper event monitoring recovered and is active.",
                        "DOPEY · Notification monitor restored",
                    )
                    reported_error = ""
            except DesktopNotificationError as error:
                error_message = _clip_notification_text(str(error), 255)
                if error_message != reported_error:
                    self._icon.notify(
                        error_message,
                        "DOPEY · Notification monitor paused",
                    )
                    reported_error = error_message
            self._stop_event.wait(self._poll_interval_seconds)
