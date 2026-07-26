"""Offline candidate discovery for the universe governor.

Reads ONLY already-fetched lane files (no network here - the supervisor stays
deterministic): the fundamentals watchlist screen, official exchange IPO
calendar, and FINRA whole-market activity scan.
Scores are documented heuristics for ORDERING the staging queue - discovery
is not edge and is stamped as such.
"""
from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from dopey_data.history_models import REQUIRED_HISTORY_UNIVERSE

from .universe_registry import record_candidate

REPO_ROOT = Path(__file__).resolve().parent.parent
MACRO_SUMMARY_PATH = REPO_ROOT / "artifacts" / "dopey" / "macro_context" / "macro_context_summary.json"
FINRA_MARKET_SCAN_PATH = REPO_ROOT / "artifacts" / "dopey" / "universe" / "finra_market_scan.json"
IPO_CALENDAR_PATH = (
    REPO_ROOT
    / "dopey_data"
    / "real"
    / "raw"
    / "macro_context"
    / "ipo_calendar.csv"
)
PUBLIC_LAKE_ROOT = REPO_ROOT / "dopey_data" / "market_lake" / "public" / "daily_ohlcv"

# ETFs/megacaps everybody knows exist are not "discoveries"; and never
# rediscover things the envelope refused or the operator retired.
DISCOVERY_SCORE_FLOOR = 0.35
MAX_CANDIDATES_PER_RUN = 500
STAGING_QUEUE_LENGTH = 500
NON_OPERATING_IPO_NAME_TERMS = (
    "acquisition",
    "blank check",
    "capital corp",
    "equity partners",
    "exchange traded fund",
    "etf",
    "gores holdings",
    "growth corp",
    "merger corp",
    "research alliance corp",
    "warrant",
    "rights",
)


def _is_operating_ipo_candidate(symbol: str, company_name: str) -> bool:
    if len(symbol) == 5 and symbol.endswith("U"):
        return False
    return not any(
        term in company_name.lower()
        for term in NON_OPERATING_IPO_NAME_TERMS
    )


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def discover_candidates(registry: dict) -> tuple[dict, list[dict]]:
    """Scan lane files, register candidates with evidence, return the scored
    discovery list (newest run only)."""
    macro = _load_json(MACRO_SUMMARY_PATH)
    scan = _load_json(FINRA_MARKET_SCAN_PATH)
    fundamentals = macro.get("fundamentals", {}) if isinstance(macro.get("fundamentals"), dict) else {}
    screen = fundamentals.get("screen", {}) if isinstance(fundamentals.get("screen"), dict) else {}

    scores: dict[str, dict] = {}

    # Source 0: the protected public lake already holds broad real OHLCV. This
    # is the lowest-cost way to widen equity research without pretending that
    # every stock must have options. Contract eligibility is checked later.
    try:
        from dopey_market_intake.public_universe_expansion_v2 import candidate_symbol_universe_v2

        public_rank = {symbol: index for index, symbol in enumerate(candidate_symbol_universe_v2())}
    except ImportError as error:
        raise RuntimeError("public universe priority registry is unavailable") from error
    public_paths = sorted(
        PUBLIC_LAKE_ROOT.glob("*.csv"),
        key=lambda path: (public_rank.get(path.stem.upper(), 10_000), path.stem.upper()),
    )
    for index, path in enumerate(public_paths):
        symbol = path.stem.upper()
        if symbol in REQUIRED_HISTORY_UNIVERSE:
            continue
        if registry.get("symbols", {}).get(symbol, {}).get("tier") in {
            "probation",
            "standby",
            "quarantined",
            "retired",
        }:
            continue
        score = max(0.45, 0.75 - 0.002 * index)
        scores[symbol] = {
            "symbol": symbol,
            "discovered_by": "protected_public_lake_inventory",
            "discovery_score": round(score, 4),
            "why": "real public OHLCV already exists locally and can expand equity-first research coverage",
            "evidence": {
                "public_path": str(path),
                "public_file_size": path.stat().st_size,
                "why": "local real-data coverage currently absent from the governed history spine",
                "options_role": "contract_selection_only_not_equity_direction",
            },
        }

    # Source 1: fundamentals watchlist names carrying excess flags but not in
    # the tradable universe - the screen already understands WHY they matter.
    for symbol, info in screen.items():
        if not isinstance(info, dict) or info.get("in_tradable_universe") is True:
            continue
        flags = info.get("excess_flags", [])
        if not isinstance(flags, list) or len(flags) < 3:
            continue
        score = min(1.0, 0.4 + 0.15 * len(flags))
        scores[symbol] = {
            "symbol": symbol,
            "discovered_by": "fundamentals_watchlist_screen",
            "discovery_score": round(score, 4),
            "why": f"{len(flags)} valuation-excess flags ({', '.join(str(f) for f in flags[:3])}...)",
            "evidence": {"excess_flags": [str(f) for f in flags], "market_cap": info.get("market_cap"), "why": "fundamental rot beyond the current universe"},
        }

    # Source 2: the official exchange IPO calendar. These names enter the
    # governed staging queue only; history, liquidity, instrument type, and
    # optional contract probes remain mandatory before research promotion.
    if IPO_CALENDAR_PATH.exists():
        reader = csv.DictReader(
            IPO_CALENDAR_PATH.read_text(encoding="utf-8").splitlines()
        )
        required = (
            "event_date",
            "symbol",
            "company_name",
            "exchange",
            "offer_price",
            "shares_offered",
            "offer_amount",
            "status",
            "source",
        )
        if tuple(reader.fieldnames or ()) != required:
            raise ValueError(
                "IPO calendar schema mismatch: "
                f"path={IPO_CALENDAR_PATH}, fields={reader.fieldnames}"
            )
        today = date.today()
        for row in reader:
            symbol = str(row.get("symbol", "")).strip().upper()
            company_name = str(row.get("company_name", "")).strip()
            if not symbol.isalpha() or not 1 <= len(symbol) <= 5:
                continue
            if not _is_operating_ipo_candidate(symbol, company_name):
                continue
            try:
                event_date = date.fromisoformat(str(row.get("event_date", "")))
            except ValueError as error:
                raise ValueError(
                    "IPO calendar contains an invalid event date: "
                    f"path={IPO_CALENDAR_PATH}, symbol={symbol}, "
                    f"event_date={row.get('event_date')!r}"
                ) from error
            age_days = (today - event_date).days
            if age_days < 0 or age_days > 730:
                continue
            raw_offer_amount = str(row.get("offer_amount", "")).strip()
            offer_amount = float(raw_offer_amount) if raw_offer_amount else None
            recency_score = max(0.0, 1.0 - age_days / 730.0)
            small_deal_score = (
                max(0.0, min(1.0, 1.0 - offer_amount / 1_000_000_000.0))
                if offer_amount is not None
                else 0.0
            )
            score = min(1.0, 0.40 + 0.35 * recency_score + 0.10 * small_deal_score)
            ipo_evidence = {
                "event_date": event_date.isoformat(),
                "listing_age_days": age_days,
                "company_name": company_name,
                "exchange": str(row.get("exchange", "")),
                "offer_price": str(row.get("offer_price", "")),
                "offer_amount": offer_amount,
                "source": str(row.get("source", "")),
                "why": "recent IPO requires governed history and reflexivity assessment",
            }
            existing = scores.get(symbol)
            if existing is not None:
                existing["discovery_score"] = round(
                    min(1.0, float(existing["discovery_score"]) + 0.25),
                    4,
                )
                existing["evidence"]["ipo"] = ipo_evidence
                existing["why"] += " + recent IPO/reflexivity exposure"
            else:
                scores[symbol] = {
                    "symbol": symbol,
                    "discovered_by": "nasdaq_ipo_calendar",
                    "discovery_score": round(score, 4),
                    "why": (
                        f"recent IPO ({age_days} days since pricing) requires "
                        "bubble/reflexivity staging"
                    ),
                    "evidence": ipo_evidence,
                }

    # Source 3: FINRA whole-market scan - persistent heavy activity or
    # short-flow extremity in names the system does not yet watch.
    for row in scan.get("most_active_non_universe", [])[:25]:
        symbol = str(row.get("symbol", ""))
        if not symbol:
            continue
        ratio = float(row.get("short_volume_ratio", 0.0) or 0.0)
        score = 0.35 + min(0.3, float(row.get("total_volume", 0)) / 400_000_000) + max(0.0, (ratio - 0.55)) * 0.8
        entry = scores.get(symbol)
        if entry:
            entry["discovery_score"] = round(min(1.0, entry["discovery_score"] + 0.2), 4)
            entry["evidence"]["finra_total_volume"] = row.get("total_volume")
            entry["evidence"]["finra_short_ratio"] = ratio
            entry["why"] += " + heavy market-wide activity"
        else:
            scores[symbol] = {
                "symbol": symbol,
                "discovered_by": "finra_market_activity_scan",
                "discovery_score": round(min(1.0, score), 4),
                "why": f"top non-universe activity ({row.get('total_volume', 0):,} shares, short-ratio {ratio})",
                "evidence": {"finra_total_volume": row.get("total_volume"), "finra_short_ratio": ratio, "scan_date": scan.get("scan_date", ""), "why": "sustained market attention the universe is blind to"},
            }

    discovered = sorted(
        (entry for entry in scores.values() if entry["discovery_score"] >= DISCOVERY_SCORE_FLOOR),
        key=lambda entry: (-entry["discovery_score"], entry["symbol"]),
    )[:MAX_CANDIDATES_PER_RUN]

    for entry in discovered:
        registry = record_candidate(
            registry, entry["symbol"], entry["discovered_by"],
            {**entry["evidence"], "discovery_score": entry["discovery_score"], "why": entry["why"]},
        )
    return registry, discovered


def build_staging_queue(registry: dict, discovered: list[dict]) -> list[dict]:
    """Ordered queue of UNSTAGED candidates for the operator ritual's network
    lane. The governor never fetches; it queues. Bounded."""
    candidate_tiers = registry.get("symbols", {})
    latest_discovery = {entry["symbol"]: entry for entry in discovered}
    for symbol, record in candidate_tiers.items():
        tier = record.get("tier")
        if tier not in {"candidate", "standby", "quarantined"} or symbol in latest_discovery:
            continue
        logs = record.get("discovery_log", []) if isinstance(record.get("discovery_log"), list) else []
        latest = logs[-1] if logs and isinstance(logs[-1], dict) else {}
        evidence = latest.get("evidence", {}) if isinstance(latest.get("evidence"), dict) else {}
        if (
            str(latest.get("discovered_by", "")) == "nasdaq_ipo_calendar"
            and not _is_operating_ipo_candidate(
                symbol,
                str(evidence.get("company_name", "")),
            )
        ):
            continue
        if tier == "quarantined":
            public_path = PUBLIC_LAKE_ROOT / f"{symbol}.csv"
            if not public_path.exists():
                continue
            latest_discovery[symbol] = {
                "symbol": symbol,
                "discovery_score": 0.8,
                "discovered_by": "quarantine_requalification_lane",
                "why": "refreshed public history can requalify a previously staged symbol through the full validator",
            }
            continue
        if tier == "standby":
            latest_membership = record.get("latest_membership_evidence", {})
            raw_prior_score = (
                latest_membership.get("selection_score")
                if isinstance(latest_membership, dict)
                else None
            )
            prior_score = (
                float(raw_prior_score)
                if isinstance(raw_prior_score, (int, float))
                else 0.55
            )
            latest_discovery[symbol] = {
                "symbol": symbol,
                "discovery_score": max(0.55, min(prior_score, 1.0)),
                "discovered_by": "standby_metadata_requalification_lane",
                "why": "inactive staged symbol requires fresh capitalization and research-tradability proof before reranking",
            }
            continue
        latest_discovery[symbol] = {
            "symbol": symbol,
            "discovery_score": float(evidence.get("discovery_score", 0.35)),
            "discovered_by": str(latest.get("discovered_by", record.get("discovered_by", "registry_candidate"))),
            "why": str(evidence.get("why", record.get("why", "governed registry candidate"))),
        }
    queue = [
        {
            "symbol": entry["symbol"],
            "discovery_score": entry["discovery_score"],
            "discovered_by": entry["discovered_by"],
            "why": entry["why"],
            "required_probes": [
                "equity_market_cap_floor_1e9_or_etf_assets_floor_250m",
                "adv_floor_5musd",
                "supported_research_instrument_type",
            ],
            "optional_contract_probe": "listed_options_available",
            "staging_path": "operator_tools/operator_universe_ritual.py",
        }
        for entry in sorted(latest_discovery.values(), key=lambda item: (-float(item["discovery_score"]), str(item["symbol"])))
        if candidate_tiers.get(entry["symbol"], {}).get("tier") in {
            "candidate",
            "standby",
            "quarantined",
        }
    ]
    return queue[:STAGING_QUEUE_LENGTH]
