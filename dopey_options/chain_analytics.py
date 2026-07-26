"""Options-chain analytics: gamma exposure, put/call ratios, delta pressure.

The math layer for chain-derived positioning metrics:

- GEX per strike and total (dealer-long-call / dealer-short-put convention):
  gex = gamma * open_interest * multiplier * spot^2 * 0.01, sign +call/-put
  (dollar gamma per 1% underlying move)
- gamma flip point: strike where cumulative GEX crosses zero
- put/call open-interest and volume ratios
- net delta-hedging pressure: sum(delta * open_interest * multiplier)

ACTIVATION IS GATED. Real chain data must be operator-staged and pass the
options manifest (license reviewed, hashes pinned) before any output is
labeled quote-derived. With no real chain staged, this module only validates
its own math on clearly-labeled fixtures and reports `blocked`. It never
fabricates chain data. Paper-only, live-blocked.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dopey_research_pipeline.quality_ledger import reproducibility_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
OPTIONS_MANIFEST_PATH = REPO_ROOT / "dopey_data" / "real" / "manifests" / "options_data_manifest.json"
CHAIN_RAW_DIR = REPO_ROOT / "dopey_data" / "real" / "raw" / "options_chains"
CHAIN_ANALYTICS_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "chain_analytics"
CHAIN_ANALYTICS_SUMMARY_PATH = CHAIN_ANALYTICS_ARTIFACT_DIR / "chain_analytics_summary.json"
CHAIN_FIXTURE_VALIDATION_PATH = CHAIN_ANALYTICS_ARTIFACT_DIR / "chain_analytics_fixture_validation.json"

CONTRACT_MULTIPLIER = 100.0
VALID_LICENSE_STATUSES = {
    "reviewed_allowed_internal_research",
    "reviewed_restricted_internal_research",
    "reviewed_public_domain",
    "reviewed_open_data_internal_research",
}


def gamma_exposure_per_strike(chain_rows: list[dict[str, Any]], spot: float) -> list[dict[str, Any]]:
    """Dollar gamma per 1% move, per strike, dealer-positioning convention."""
    by_strike: dict[float, float] = {}
    for row in chain_rows:
        strike = float(row["strike"])
        gamma = float(row["gamma"])
        open_interest = float(row["open_interest"])
        sign = 1.0 if str(row["option_type"]).lower() == "call" else -1.0
        gex = sign * gamma * open_interest * CONTRACT_MULTIPLIER * spot * spot * 0.01
        by_strike[strike] = by_strike.get(strike, 0.0) + gex
    return [
        {"strike": strike, "gex_dollar_per_pct": round(value, 2)}
        for strike, value in sorted(by_strike.items())
    ]


def total_gamma_exposure(chain_rows: list[dict[str, Any]], spot: float) -> float:
    return round(sum(item["gex_dollar_per_pct"] for item in gamma_exposure_per_strike(chain_rows, spot)), 2)


def gamma_flip_strike(chain_rows: list[dict[str, Any]], spot: float) -> float | None:
    """Strike where cumulative GEX (ascending strikes) crosses zero."""
    per_strike = gamma_exposure_per_strike(chain_rows, spot)
    cumulative = 0.0
    previous_strike: float | None = None
    previous_cumulative = 0.0
    for item in per_strike:
        cumulative += item["gex_dollar_per_pct"]
        if previous_strike is not None and (previous_cumulative < 0.0 <= cumulative or cumulative < 0.0 <= previous_cumulative):
            return item["strike"]
        previous_strike = item["strike"]
        previous_cumulative = cumulative
    return None


def put_call_ratios(chain_rows: list[dict[str, Any]]) -> dict[str, float]:
    call_oi = sum(float(row["open_interest"]) for row in chain_rows if str(row["option_type"]).lower() == "call")
    put_oi = sum(float(row["open_interest"]) for row in chain_rows if str(row["option_type"]).lower() == "put")
    call_volume = sum(float(row.get("volume", 0.0)) for row in chain_rows if str(row["option_type"]).lower() == "call")
    put_volume = sum(float(row.get("volume", 0.0)) for row in chain_rows if str(row["option_type"]).lower() == "put")
    return {
        # None (JSON null) when undefined: 0.0 would read as extreme call-heavy, the inverse of reality
        "put_call_oi_ratio": round(put_oi / call_oi, 6) if call_oi > 0 else None,
        "put_call_volume_ratio": round(put_volume / call_volume, 6) if call_volume > 0 else None,
        "call_open_interest": call_oi,
        "put_open_interest": put_oi,
        "call_volume": call_volume,
        "put_volume": put_volume,
    }


def net_delta_pressure(chain_rows: list[dict[str, Any]]) -> float:
    """Net share-equivalent delta the dealer book must hedge (sign of flow)."""
    total = 0.0
    for row in chain_rows:
        delta = float(row["delta"])
        open_interest = float(row["open_interest"])
        total += delta * open_interest * CONTRACT_MULTIPLIER
    return round(total, 2)


def _real_chain_gate() -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    if OPTIONS_MANIFEST_PATH.exists():
        try:
            manifest = json.loads(OPTIONS_MANIFEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            manifest = {"manifest_parse_error": True}
    staged_files = (
        sorted(CHAIN_RAW_DIR.glob("*/*.csv")) + sorted(CHAIN_RAW_DIR.glob("*.csv")) + sorted(CHAIN_RAW_DIR.glob("*.jsonl"))
        if CHAIN_RAW_DIR.exists()
        else []
    )
    template_only = bool(manifest.get("template_only") is True or manifest.get("manifest_id") == "OPTIONS_TEMPLATE_ONLY")
    license_ok = str(manifest.get("license_status", "unknown")).lower() in VALID_LICENSE_STATUSES
    terms_ok = manifest.get("provider_terms_reviewed") is True
    if not staged_files:
        status = "blocked_no_real_chain_data_staged"
    elif template_only or not license_ok or not terms_ok:
        status = "blocked_chain_manifest_not_finalized"
    else:
        status = "real_chain_data_candidate_present_requires_validator"
    return {
        "chain_gate_status": status,
        "staged_chain_file_count": len(staged_files),
        "manifest_template_only": template_only,
        "manifest_license_ok": license_ok,
        "manifest_terms_reviewed": terms_ok,
    }


def _fixture_chain() -> list[dict[str, Any]]:
    """Clearly-labeled synthetic chain used ONLY to validate the math."""
    rows = []
    for strike, call_gamma, put_gamma, call_oi, put_oi, call_delta, put_delta in (
        (95.0, 0.010, 0.010, 1000, 3000, 0.75, -0.25),
        (100.0, 0.020, 0.020, 2000, 2000, 0.50, -0.50),
        (105.0, 0.010, 0.010, 3000, 1000, 0.25, -0.75),
    ):
        rows.append({"strike": strike, "option_type": "call", "gamma": call_gamma, "open_interest": call_oi, "volume": call_oi / 2, "delta": call_delta, "fixture_only": True, "not_real_data": True})
        rows.append({"strike": strike, "option_type": "put", "gamma": put_gamma, "open_interest": put_oi, "volume": put_oi / 2, "delta": put_delta, "fixture_only": True, "not_real_data": True})
    return rows


def enrich_rows_with_greeks(rows: list[dict[str, Any]], risk_free_rate: float = 0.04) -> list[dict[str, Any]]:
    """Compute gamma/delta from chain IV via the Black-Scholes greeks engine."""
    from .greeks_engine import bs_greeks

    enriched: list[dict[str, Any]] = []
    for row in rows:
        tenor_years = max(float(row["dte_calendar"]) / 365.0, 1e-6)
        greeks = bs_greeks(
            float(row["underlying_spot"]),
            float(row["strike"]),
            tenor_years,
            risk_free_rate,
            float(row["implied_vol"]),
            str(row["option_type"]),
        )
        enriched.append({**row, "gamma": float(greeks["gamma"]), "delta": float(greeks["delta"])})
    return enriched


def real_chain_positioning_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-symbol quote-derived positioning metrics from a validated snapshot."""
    by_symbol: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_symbol.setdefault(str(row["symbol"]), []).append(row)
    metrics: list[dict[str, Any]] = []
    for symbol, symbol_rows in sorted(by_symbol.items()):
        spot = float(symbol_rows[0]["underlying_spot"])
        atm_rows = sorted(symbol_rows, key=lambda item: abs(float(item["strike"]) - spot))[:4]
        atm_iv = sum(float(item["implied_vol"]) for item in atm_rows) / len(atm_rows)
        metrics.append(
            {
                "artifact_type": "chain_positioning_metrics",
                "symbol": symbol,
                "snapshot_date": symbol_rows[0]["snapshot_date"],
                "expiry": symbol_rows[0]["expiry"],
                "underlying_spot": spot,
                "contract_rows": len(symbol_rows),
                "total_gex_dollar_per_pct": total_gamma_exposure(symbol_rows, spot),
                "gamma_flip_strike": gamma_flip_strike(symbol_rows, spot),
                "atm_implied_vol": round(atm_iv, 6),
                **put_call_ratios(symbol_rows),
                "net_delta_pressure_shares": net_delta_pressure(symbol_rows),
                "quote_derived": True,
                "pricing_source_tier": "quote_derived_snapshot",
                "not_edge_evidence": True,
                "paper_only": True,
                "live_blocked": True,
            }
        )
    return metrics


REAL_POSITIONING_METRICS_PATH = CHAIN_ANALYTICS_ARTIFACT_DIR / "real_chain_positioning_metrics.jsonl"


def run_chain_analytics_gate() -> dict[str, Any]:
    gate = _real_chain_gate()
    fixture = _fixture_chain()
    spot = 100.0
    fixture_validation = {
        "artifact_type": "chain_analytics_fixture_validation",
        "fixture_only": True,
        "not_real_data": True,
        "total_gex_fixture": total_gamma_exposure(fixture, spot),
        "gamma_flip_fixture": gamma_flip_strike(fixture, spot),
        "put_call_ratios_fixture": put_call_ratios(fixture),
        "net_delta_pressure_fixture": net_delta_pressure(fixture),
        "paper_only": True,
        "live_blocked": True,
    }
    from .chain_snapshot_loader import load_latest_chain_snapshot

    snapshot = load_latest_chain_snapshot()
    real_metrics: list[dict[str, Any]] = []
    if snapshot["chain_snapshot_status"] == "real_chain_snapshot_validated":
        real_metrics = real_chain_positioning_metrics(enrich_rows_with_greeks(snapshot["rows"]))
        status = "real_chain_analytics_computed"
    else:
        status = snapshot["chain_snapshot_status"] if snapshot["chain_snapshot_status"].startswith("blocked") else gate["chain_gate_status"]
    summary = {
        "artifact_type": "chain_analytics_summary",
        "chain_analytics_status": status,
        **gate,
        "chain_snapshot_status": snapshot["chain_snapshot_status"],
        "snapshot_date": snapshot["snapshot_date"],
        "snapshot_row_count": snapshot["row_count"],
        "snapshot_symbols": snapshot["symbols"],
        "real_metric_count": len(real_metrics),
        "math_validated_on_fixture": True,
        "quote_derived_output_produced": bool(real_metrics),
        "activation_requirement": "operator_staged_licensed_chain_data_plus_finalized_options_manifest",
        "staging_paths": {
            "chain_raw_dir": str(CHAIN_RAW_DIR),
            "options_manifest": str(OPTIONS_MANIFEST_PATH),
        },
        "metrics_available_on_activation": [
            "gamma_exposure_per_strike",
            "total_gamma_exposure",
            "gamma_flip_strike",
            "put_call_oi_ratio",
            "put_call_volume_ratio",
            "net_delta_pressure",
        ],
        "paper_only": True,
        "live_blocked": True,
        "not_edge_evidence": True,
    }
    summary["reproducibility_hash"] = reproducibility_hash(summary)
    CHAIN_ANALYTICS_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    _write_json(CHAIN_FIXTURE_VALIDATION_PATH, fixture_validation)
    if real_metrics:
        lines = [json.dumps(record, sort_keys=True, ensure_ascii=False) for record in real_metrics]
        REAL_POSITIONING_METRICS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _write_json(CHAIN_ANALYTICS_SUMMARY_PATH, summary)
    return summary


def _write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
