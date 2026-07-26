"""Run the DOPEY chart vision engine."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from dopey_wealth_engine.common import ARTIFACT_ROOT, DATA_ROOT, proof_record, read_csv, read_json, read_jsonl, stable_hash, write_json, write_jsonl

from .chart_pattern_detector import detect_chart_patterns
from .chart_renderer import render_chart_artifacts
from .indicator_engine import build_indicator_rows


ARTIFACT_DIR = ARTIFACT_ROOT / "chart_vision"
HTML_ROOT = ARTIFACT_DIR / "charts" / "html"
PNG_ROOT = ARTIFACT_DIR / "charts" / "png"
SPEC_ROOT = ARTIFACT_DIR / "charts" / "specs"
FEATURES_PATH = ARTIFACT_DIR / "chart_feature_records.jsonl"
PATTERNS_PATH = ARTIFACT_DIR / "chart_pattern_records.jsonl"
OVERLAYS_PATH = ARTIFACT_DIR / "chart_signal_overlay_records.jsonl"
SUMMARY_PATH = ARTIFACT_DIR / "chart_vision_summary.json"
PROOF_PATH = ARTIFACT_DIR / "chart_vision_proof.jsonl"


def run_chart_vision_engine() -> dict:
    manifest = read_json(DATA_ROOT / "market_lake" / "manifests" / "market_lake_manifest.json")
    files = manifest.get("files", []) if isinstance(manifest.get("files", []), list) else []
    all_features: list[dict] = []
    all_patterns: list[dict] = []
    overlays: list[dict] = []
    specs: list[dict] = []
    for file_record in files:
        symbol = str(file_record["symbol"])
        rows = read_csv(Path(str(file_record["path"])))
        if not rows:
            continue
        features = build_indicator_rows(symbol, rows)
        data_tier = str(file_record.get("data_tier", "market_vision"))
        source_type = str(file_record.get("market_data_source_type", "fixture_fallback" if file_record.get("source") == "fixture_fallback" else "public_live_fetch"))
        for feature in features:
            feature["data_tier"] = data_tier
            feature["market_data_source_type"] = source_type
        patterns = detect_chart_patterns(symbol, features, data_tier)
        for pattern in patterns:
            pattern["market_data_source_type"] = source_type
        spec = render_chart_artifacts(symbol, rows, features, HTML_ROOT / f"{symbol}.html", PNG_ROOT / f"{symbol}.png", SPEC_ROOT / f"{symbol}.json")
        spec["market_data_source_type"] = source_type
        all_features.extend(features[-260:])
        all_patterns.extend(patterns)
        specs.append(spec)
        for pattern in patterns:
            overlay = {
                "artifact_type": "chart_signal_overlay_record",
                "symbol": symbol,
                "timestamp": pattern["timestamp"],
                "overlay_type": "long_call" if pattern["direction"] == "bullish" else ("long_put" if pattern["direction"] == "bearish" else "no_trade"),
                "pattern_name": pattern["pattern_name"],
                "data_tier": data_tier,
                "market_data_source_type": source_type,
                "paper_only": True,
                "live_blocked": True,
            }
            overlay["record_hash"] = stable_hash(overlay)
            overlays.append(overlay)
    for record in all_features:
        record["record_hash"] = stable_hash(record)
    for record in all_patterns:
        record["record_hash"] = stable_hash(record)
    trend_counts = Counter(str(record.get("trend_regime", "")) for record in all_features)
    summary = {
        "artifact_type": "chart_vision_summary",
        "chart_vision_version": "dopey-chart-vision-v1",
        "chart_vision_status": "charts_generated" if specs else "blocked_no_market_data",
        "chart_count": len(specs),
        "html_chart_count": len(specs),
        "png_chart_count": len(specs),
        "feature_record_count": len(all_features),
        "pattern_record_count": len(all_patterns),
        "overlay_record_count": len(overlays),
        "trend_regime_counts": dict(sorted(trend_counts.items())),
        "plotly_available": False,
        "matplotlib_available": False,
        "fallback_renderer": "stdlib_svg_and_png",
        "paper_only": True,
        "live_blocked": True,
    }
    summary["summary_hash"] = stable_hash(summary)
    write_jsonl(FEATURES_PATH, all_features, False)
    write_jsonl(PATTERNS_PATH, all_patterns, False)
    write_jsonl(OVERLAYS_PATH, overlays, False)
    write_json(SUMMARY_PATH, summary)
    write_jsonl(PROOF_PATH, [proof_record("chart-vision-engine", summary["chart_vision_status"], summary)], False)
    return {**summary, "artifact_paths": artifact_paths()}


def artifact_paths() -> dict[str, str]:
    return {
        "chart_feature_records": str(FEATURES_PATH),
        "chart_pattern_records": str(PATTERNS_PATH),
        "chart_signal_overlay_records": str(OVERLAYS_PATH),
        "chart_vision_summary": str(SUMMARY_PATH),
        "chart_vision_proof": str(PROOF_PATH),
        "chart_html_root": str(HTML_ROOT),
        "chart_png_root": str(PNG_ROOT),
    }


def main() -> int:
    summary = run_chart_vision_engine()
    print(json.dumps({
        "chart_vision_status": summary["chart_vision_status"],
        "chart_count": summary["chart_count"],
        "summary_path": summary["artifact_paths"]["chart_vision_summary"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
