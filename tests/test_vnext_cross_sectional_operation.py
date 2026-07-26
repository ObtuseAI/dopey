"""Integration coverage for resumable cross-sectional vNext operation."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from dopey.macro import credit as credit_module
from dopey.runtime import cross_sectional_vnext as cross_sectional_module
from dopey.runtime.cross_sectional_vnext import run_cross_sectional_vnext
from dopey.technical import history_adapter
from tests.public_source_fixtures import (
    build_synthetic_history_rows,
    write_empty_vnext_governed_inputs,
    write_synthetic_histories_manifest,
)


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
VNEXT_FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "vnext"


def _market_time() -> str:
    context = json.loads((VNEXT_FIXTURE_ROOT / "cross_asset_context.json").read_text(encoding="utf-8"))
    market_date = datetime.fromisoformat(str(context["decision_date"])).date()
    close_et = datetime.combine(market_date, time(16, 0), tzinfo=ZoneInfo("America/New_York"))
    return close_et.astimezone(timezone.utc).isoformat()


def _mutable_run_inputs(repository_root: Path) -> dict[str, Path]:
    context_root = repository_root / "context"
    context_root.mkdir(parents=True, exist_ok=True)
    cross_asset = context_root / "cross_asset_context.json"
    news = context_root / "news_context.json"
    shutil.copy2(VNEXT_FIXTURE_ROOT / "cross_asset_context.json", cross_asset)
    shutil.copy2(VNEXT_FIXTURE_ROOT / "news_context.json", news)
    governed = write_empty_vnext_governed_inputs(
        repository_root,
        "2026-07-14T20:45:00+00:00",
    )
    return {
        "cross_asset": cross_asset,
        "news": news,
        "macro": governed["macro_manifest"],
        "options": governed["options_manifest"],
        "earnings": governed["earnings_directory"],
    }


def _causally_valid_event_time(inputs: dict[str, Path], market_time: str) -> str:
    timestamps = [datetime.fromisoformat(market_time.replace("Z", "+00:00"))]
    news = json.loads(inputs["news"].read_text(encoding="utf-8"))
    timestamps.append(
        datetime.fromisoformat(str(news["decision_time"]).replace("Z", "+00:00"))
    )
    for key in ("macro", "options"):
        manifest = json.loads(inputs[key].read_text(encoding="utf-8"))
        timestamps.append(
            datetime.fromisoformat(str(manifest["created_at"]).replace("Z", "+00:00"))
        )
    return (max(timestamps) + timedelta(minutes=1)).isoformat()


def test_cross_sectional_vnext_is_resumable_and_ledger_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    market_time = _market_time()
    repository_root = tmp_path / "repository"
    inputs = _mutable_run_inputs(repository_root)
    history_manifest = write_synthetic_histories_manifest(
        repository_root / "dopey_data" / "history",
        {
            "QQQ": build_synthetic_history_rows("QQQ", 260),
            "SPY": build_synthetic_history_rows("SPY", 260),
        },
    )
    monkeypatch.setattr(
        cross_sectional_module,
        "HISTORY_MANIFEST_PATH",
        history_manifest,
    )
    monkeypatch.setattr(history_adapter, "HISTORY_MANIFEST_PATH", history_manifest)
    monkeypatch.setattr(credit_module, "HISTORY_MANIFEST_PATH", history_manifest)
    event_time = _causally_valid_event_time(inputs, market_time)
    output_root = tmp_path / "cross-sectional"
    arguments = (
        ("SPY", "QQQ"),
        "breakout",
        event_time,
        market_time,
        output_root,
        repository_root,
        inputs["cross_asset"],
        inputs["news"],
        inputs["macro"],
        inputs["options"],
        inputs["earnings"],
    )
    first = run_cross_sectional_vnext(*arguments)
    session_input_roots = [
        path
        for path in (output_root / "inputs" / market_time[:10]).iterdir()
        if path.is_dir()
    ]
    assert len(session_input_roots) == 1
    news_snapshot = session_input_roots[0] / "news_context.json"
    immutable_news = news_snapshot.read_bytes()
    mutated_news: dict[str, Any] = json.loads(inputs["news"].read_text(encoding="utf-8"))
    mutated_news["decision_time"] = "2026-07-15T00:00:00+00:00"
    inputs["news"].write_text(json.dumps(mutated_news, sort_keys=True) + "\n", encoding="utf-8")
    second = run_cross_sectional_vnext(*arguments)

    assert first["batch_status"] == "complete_awaiting_forward_settlement"
    assert first["completed_symbol_count"] == 2
    assert first["pending_count"] == 2
    assert first["action_ready"] is False
    assert first["paper_only"] is True and first["live_blocked"] is True
    assert second["batch_fingerprint"] == first["batch_fingerprint"]
    assert second["reproducibility_hash"] == first["reproducibility_hash"]
    assert news_snapshot.read_bytes() == immutable_news
    prediction_lines = (output_root / "forward_predictions.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(prediction_lines) == 2
    cross_section_snapshot = session_input_roots[0] / "cross_sectional_context.json"
    tampered_cross_section: dict[str, Any] = json.loads(cross_section_snapshot.read_text(encoding="utf-8"))
    source_hashes = tampered_cross_section.get("source_hashes")
    if not isinstance(source_hashes, dict):
        raise TypeError("test cross-sectional snapshot source_hashes must be an object")
    source_hashes["SPY"] = "0" * 64
    cross_section_snapshot.write_text(
        json.dumps(tampered_cross_section, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="history sources drifted"):
        run_cross_sectional_vnext(*arguments)
