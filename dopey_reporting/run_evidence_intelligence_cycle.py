"""Refresh the cohesive dossier, mutation graph, and pricing-oracle evidence spine."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from dopey_evolution.mutation_genealogy import build_mutation_genealogy
from dopey_options.binomial_oracle import run_binomial_oracle_validation
from dopey.protocols.artifact_contracts import (
    assert_artifact_record,
    audit_evidence_artifact_bundle,
)

from .strategy_evidence_dossier import build_strategy_evidence_dossier, default_dossier_source_paths


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = REPOSITORY_ROOT / "artifacts" / "dopey" / "evidence_intelligence"


def run_evidence_intelligence_cycle(repository_root: Path, output_root: Path) -> dict[str, object]:
    """Refresh every evidence-intelligence surface in dependency order."""

    dossier = build_strategy_evidence_dossier(
        repository_root,
        default_dossier_source_paths(repository_root),
        repository_root / "artifacts" / "dopey" / "runs",
        repository_root / "artifacts" / "dopey" / "runs" / "latest_dossier.json",
    )
    mutation = build_mutation_genealogy(
        repository_root / "artifacts" / "dopey" / "mutations" / "mutation_registry.jsonl",
        repository_root / "artifacts" / "dopey" / "runs" / "latest_dossier.json",
        repository_root / "artifacts" / "dopey" / "evolution" / "mutation_genealogy.json",
    )
    oracle = run_binomial_oracle_validation(
        repository_root / "artifacts" / "dopey" / "options_oracle" / "binomial_oracle_validation.json"
    )
    capital = _read_json_object(
        repository_root / "artifacts" / "dopey" / "runs" / "latest_capital_exposure.json"
    )
    contract_audit = audit_evidence_artifact_bundle(
        repository_root,
        repository_root / "artifacts" / "dopey" / "contracts" / "latest_bundle_audit.json",
    )
    result: dict[str, object] = {
        "artifact_type": "evidence_intelligence_cycle",
        "cycle_version": "dopey-evidence-intelligence-cycle-v2",
        "cycle_status": "complete",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "dossier_status": dossier["dossier_status"],
        "dossier_run_id": dossier["run_id"],
        "eligible_candidate_count": dossier["eligible_candidate_count"],
        "mutation_explorer_status": mutation["explorer_status"],
        "mutation_node_count": mutation["node_count"],
        "oracle_validation_status": oracle["validation_status"],
        "oracle_passed_test_count": oracle["passed_test_count"],
        "capital_normalization_status": capital["normalization_status"],
        "contract_audit_status": contract_audit["audit_status"],
        "contract_registry_hash": contract_audit["contract_registry_hash"],
        "promotion_allowed": False,
        "profitability_claim_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    assert_artifact_record("evidence_cycle", result)
    output_root.mkdir(parents=True, exist_ok=True)
    temporary = output_root / "latest_cycle.json.tmp"
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output_root / "latest_cycle.json")
    return result


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"evidence intelligence source is missing: path={path}")
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict) or not all(isinstance(key, str) for key in parsed):
        raise TypeError(f"evidence intelligence source must be a JSON object: path={path}")
    return parsed


def main() -> int:
    result = run_evidence_intelligence_cycle(REPOSITORY_ROOT, OUTPUT_ROOT)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
