"""Universe registry: tiers, provenance, and the active-universe resolution.

Every symbol the system watches carries its full story: which lane discovered
it, on what evidence, when it was staged, how it has behaved since, and - if
it leaves - why. "Self-understanding" means no symbol is ever just a string.

Tiers
-----
core        - the code-floor universe (REQUIRED_HISTORY_UNIVERSE). Governance
              anchor: NEVER auto-added, NEVER auto-retired, NEVER quarantined
              by machinery. Changing core is a human code change.
probation   - discovered, probed, staged, and selected by the evolving
              evidence policy. Full research citizens while current
              attention, liquidity, capitalization, and research
              tradability remain eligible.
candidate   - discovered and scored, NOT yet staged. No data fetched beyond
              the discovery evidence itself.
standby     - previously staged but currently outside the evolving active
              universe. Data and membership history are retained; a fresh
              evidence cycle can promote it again without inventing history.
quarantined - a probation name that went mechanically dead (unfetchable or
              lagging the core frontier), excluded from the active universe
              and from uniform-advance so it cannot freeze the spine. Data
              retained; reversible.
retired     - a human-confirmed removal. Data retained forever.

The registry is an artifact (auto-mirrored under test isolation); the code
floor stays the authority the validator enforces.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dopey_data.history_models import REQUIRED_HISTORY_UNIVERSE
from dopey.protocols.identity import canonical_hash
from dopey_research_pipeline.artifact_io import write_json_atomic

REPO_ROOT = Path(__file__).resolve().parent.parent
UNIVERSE_ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "universe"
UNIVERSE_REGISTRY_PATH = UNIVERSE_ARTIFACT_DIR / "universe_registry.json"

TIERS = ("core", "probation", "candidate", "standby", "quarantined", "retired")
UNIVERSE_CAPACITY_POLICY = "evolving_ranked_cap"
MAX_ACTIVE_UNIVERSE_SIZE = 500
MAX_PROBATION_SYMBOLS = MAX_ACTIVE_UNIVERSE_SIZE - len(REQUIRED_HISTORY_UNIVERSE)
QUARANTINE_FRONTIER_LAG_SESSIONS = 3
MEMBERSHIP_POLICY_VERSION = "dopey-evolving-universe-v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_registry() -> dict:
    return {
        "artifact_type": "universe_registry",
        "universe_registry_version": "dopey-universe-registry-v3",
        "capacity_policy": UNIVERSE_CAPACITY_POLICY,
        "maximum_active_universe_size": MAX_ACTIVE_UNIVERSE_SIZE,
        "symbols": {},
        "updated_utc": "",
        "paper_only": True,
        "live_blocked": True,
    }


def load_registry() -> dict:
    try:
        record = json.loads(UNIVERSE_REGISTRY_PATH.read_text(encoding="utf-8"))
        if isinstance(record, dict) and isinstance(record.get("symbols"), dict):
            record["universe_registry_version"] = "dopey-universe-registry-v3"
            record["capacity_policy"] = UNIVERSE_CAPACITY_POLICY
            record["maximum_active_universe_size"] = MAX_ACTIVE_UNIVERSE_SIZE
            return record
    except (OSError, json.JSONDecodeError):
        pass
    return _empty_registry()


def save_registry(registry: dict) -> None:
    UNIVERSE_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    registry["universe_registry_version"] = "dopey-universe-registry-v3"
    registry["capacity_policy"] = UNIVERSE_CAPACITY_POLICY
    registry["maximum_active_universe_size"] = MAX_ACTIVE_UNIVERSE_SIZE
    registry["updated_utc"] = _now()
    write_json_atomic(UNIVERSE_REGISTRY_PATH, registry, keep_backup=True)


def core_universe() -> tuple[str, ...]:
    return tuple(REQUIRED_HISTORY_UNIVERSE)


def active_universe(registry: dict | None = None) -> tuple[str, ...]:
    """Code floor plus staged probation names. Candidates, quarantined, and
    retired names are NOT active. Deterministic ordering."""
    registry = registry if registry is not None else load_registry()
    extras = sorted(
        symbol
        for symbol, record in registry.get("symbols", {}).items()
        if record.get("tier") == "probation" and symbol not in REQUIRED_HISTORY_UNIVERSE
    )
    return tuple(REQUIRED_HISTORY_UNIVERSE) + tuple(extras)


def probation_symbols(registry: dict | None = None) -> tuple[str, ...]:
    registry = registry if registry is not None else load_registry()
    return tuple(sorted(
        symbol for symbol, record in registry.get("symbols", {}).items()
        if record.get("tier") == "probation"
    ))


def symbol_tier(symbol: str, registry: dict | None = None) -> str:
    if symbol in REQUIRED_HISTORY_UNIVERSE:
        return "core"
    registry = registry if registry is not None else load_registry()
    return str(registry.get("symbols", {}).get(symbol, {}).get("tier", ""))


def record_candidate(registry: dict, symbol: str, discovered_by: str, evidence: dict) -> dict:
    """Register (or refresh) a discovery. Never touches core; never demotes a
    staged name back to candidate."""
    symbol = symbol.upper().strip()
    if not symbol or symbol in REQUIRED_HISTORY_UNIVERSE:
        return registry
    existing = registry["symbols"].get(symbol, {})
    if existing.get("tier") in {
        "candidate",
        "probation",
        "standby",
        "quarantined",
        "retired",
    }:
        # keep the richer story; append the fresh sighting to its evidence log
        existing.setdefault("discovery_log", []).append(
            {"seen_utc": _now(), "discovered_by": discovered_by, "evidence": evidence}
        )
        registry["symbols"][symbol] = existing
        return registry
    record = {
        "tier": "candidate",
        "first_seen_utc": existing.get("first_seen_utc", _now()),
        "discovered_by": discovered_by,
        "discovery_log": existing.get("discovery_log", []) + [
            {"seen_utc": _now(), "discovered_by": discovered_by, "evidence": evidence}
        ],
        "why": evidence.get("why", ""),
        "membership_history": list(existing.get("membership_history", [])),
        "paper_only": True,
        "live_blocked": True,
    }
    _append_membership_event(
        record,
        from_tier=str(existing.get("tier", "unregistered")),
        to_tier="candidate",
        decision="candidate_registered",
        reason_codes=("governed_discovery_evidence_recorded",),
        evidence_hash=canonical_hash(evidence),
        observed_at_utc=str(record["first_seen_utc"]),
    )
    registry["symbols"][symbol] = record
    return registry


def _append_membership_event(
    record: dict[str, Any],
    from_tier: str,
    to_tier: str,
    decision: str,
    reason_codes: tuple[str, ...],
    evidence_hash: str,
    observed_at_utc: str,
) -> None:
    body = {
        "policy_version": MEMBERSHIP_POLICY_VERSION,
        "observed_at_utc": observed_at_utc,
        "from_tier": from_tier,
        "to_tier": to_tier,
        "decision": decision,
        "reason_codes": list(reason_codes),
        "evidence_hash": evidence_hash,
    }
    event = {**body, "event_id": canonical_hash(body)}
    history = record.setdefault("membership_history", [])
    if not isinstance(history, list):
        raise TypeError("registry membership_history must be a list")
    if not any(isinstance(item, dict) and item.get("event_id") == event["event_id"] for item in history):
        history.append(event)


def record_staging_proof(registry: dict, symbol: str, staging_proof: dict) -> dict:
    """Retain validated staging evidence without selecting active membership."""

    record = registry.get("symbols", {}).get(symbol)
    if not isinstance(record, dict) or record.get("tier") not in {
        "candidate",
        "standby",
        "quarantined",
    }:
        return registry
    required = {
        "staged_rows",
        "staged_frontier",
        "options_available",
        "validator_status",
        "market_cap",
        "fund_assets",
        "instrument_type",
        "capitalization_kind",
        "capitalization_value",
        "adv_usd",
        "research_tradable",
        "probe_observed_at_utc",
    }
    missing = sorted(required - set(staging_proof))
    if missing:
        record.setdefault("notes", []).append(
            f"staging_proof_refused_missing_{'+'.join(missing)}"
        )
        return registry
    if staging_proof["validator_status"] != "valid_real_dataset":
        record.setdefault("notes", []).append("staging_proof_refused_invalid_dataset")
        return registry
    previous_tier = str(record["tier"])
    record["tier"] = "standby"
    record["staged_utc"] = str(staging_proof["probe_observed_at_utc"])
    record["staging_proof"] = dict(staging_proof)
    _append_membership_event(
        record,
        from_tier=previous_tier,
        to_tier="standby",
        decision="staging_validated_awaiting_evolution_selection",
        reason_codes=("validated_history_staged", "membership_selection_pending"),
        evidence_hash=canonical_hash(staging_proof),
        observed_at_utc=str(staging_proof["probe_observed_at_utc"]),
    )
    registry["symbols"][symbol] = record
    return registry


def promote_to_probation(registry: dict, symbol: str, staging_proof: dict) -> dict:
    """Select staged candidate/standby evidence for active research.

    The evolving-universe engine is the only routine caller. Operator staging
    records a standby proof and cannot directly activate a symbol.
    """
    record = registry["symbols"].get(symbol)
    if not record or record.get("tier") not in {"candidate", "standby"}:
        return registry
    if len(probation_symbols(registry)) >= MAX_PROBATION_SYMBOLS:
        record.setdefault("notes", []).append("promotion_deferred_universe_cap")
        return registry
    required = {
        "staged_rows",
        "staged_frontier",
        "options_available",
        "validator_status",
        "market_cap",
        "fund_assets",
        "instrument_type",
        "capitalization_kind",
        "capitalization_value",
        "adv_usd",
        "research_tradable",
        "probe_observed_at_utc",
        "membership_evidence",
    }
    if not required.issubset(staging_proof):
        record.setdefault("notes", []).append("promotion_refused_incomplete_staging_proof")
        return registry
    membership_evidence = staging_proof.get("membership_evidence")
    if not isinstance(membership_evidence, dict):
        record.setdefault("notes", []).append("promotion_refused_invalid_membership_evidence")
        return registry
    membership_required = {
        "policy_version",
        "decision_time_utc",
        "evidence_hash",
        "selection_score",
        "rank",
        "reason_codes",
    }
    if not membership_required.issubset(membership_evidence):
        record.setdefault("notes", []).append("promotion_refused_incomplete_membership_evidence")
        return registry
    if staging_proof["validator_status"] != "valid_real_dataset":
        record.setdefault("notes", []).append("promotion_refused_invalid_dataset")
        return registry
    if staging_proof["research_tradable"] is not True:
        record.setdefault("notes", []).append("promotion_refused_not_research_tradable")
        return registry
    previous_tier = str(record["tier"])
    record["tier"] = "probation"
    record["staged_utc"] = str(staging_proof["probe_observed_at_utc"])
    record["staging_proof"] = dict(staging_proof)
    record["latest_membership_evidence"] = dict(membership_evidence)
    _append_membership_event(
        record,
        from_tier=previous_tier,
        to_tier="probation",
        decision="promoted_to_active_research",
        reason_codes=tuple(str(value) for value in membership_evidence["reason_codes"]),
        evidence_hash=str(membership_evidence["evidence_hash"]),
        observed_at_utc=str(membership_evidence["decision_time_utc"]),
    )
    registry["symbols"][symbol] = record
    return registry


def demote_to_standby(
    registry: dict,
    symbol: str,
    reason_codes: tuple[str, ...],
    membership_evidence: dict,
) -> dict:
    """Demote a non-core active symbol while retaining every staged artifact."""

    record = registry.get("symbols", {}).get(symbol)
    if not isinstance(record, dict) or record.get("tier") != "probation":
        return registry
    if not reason_codes:
        raise ValueError("universe demotion requires at least one reason code")
    decision_time = membership_evidence.get("decision_time_utc")
    evidence_hash = membership_evidence.get("evidence_hash")
    if not isinstance(decision_time, str) or not isinstance(evidence_hash, str):
        raise ValueError("universe demotion requires decision_time_utc and evidence_hash")
    record["tier"] = "standby"
    record["latest_membership_evidence"] = dict(membership_evidence)
    record["demoted_utc"] = decision_time
    record["demotion_reason_codes"] = list(reason_codes)
    _append_membership_event(
        record,
        from_tier="probation",
        to_tier="standby",
        decision="demoted_from_active_research",
        reason_codes=reason_codes,
        evidence_hash=evidence_hash,
        observed_at_utc=decision_time,
    )
    registry["symbols"][symbol] = record
    return registry


def quarantine(registry: dict, symbol: str, reason: str) -> dict:
    """Mechanical-death quarantine for PROBATION names only (unfetchable /
    frontier-lagging). Core is untouchable; quality complaints go through
    recommendations, not here."""
    record = registry["symbols"].get(symbol)
    if not record or record.get("tier") != "probation":
        return registry
    record["tier"] = "quarantined"
    record["quarantined_utc"] = _now()
    record["quarantine_reason"] = reason
    _append_membership_event(
        record,
        from_tier="probation",
        to_tier="quarantined",
        decision="mechanical_quarantine",
        reason_codes=(reason,),
        evidence_hash=canonical_hash({"symbol": symbol, "reason": reason}),
        observed_at_utc=str(record["quarantined_utc"]),
    )
    registry["symbols"][symbol] = record
    return registry


def unquarantine(registry: dict, symbol: str, staging_proof: dict) -> dict:
    record = registry["symbols"].get(symbol)
    if not record or record.get("tier") != "quarantined":
        return registry
    return record_staging_proof(registry, symbol, staging_proof)


def tier_counts(registry: dict | None = None) -> dict[str, int]:
    registry = registry if registry is not None else load_registry()
    counts = {tier: 0 for tier in TIERS}
    counts["core"] = len(REQUIRED_HISTORY_UNIVERSE)
    for record in registry.get("symbols", {}).values():
        tier = str(record.get("tier", ""))
        if tier in counts and tier != "core":
            counts[tier] += 1
    return counts
