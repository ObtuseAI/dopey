"""OPERATOR TOOL - one-command candidate evaluation for the squeeze family.

The DOPEY-grade version of "agent builds a strategy and backtests it": take
the bb_squeeze_breakout archetype from idea to an HONEST verdict in one run.

    1. Run the two-question compression study over the governed spine
       (range question + direction question, era-split, null-calibrated,
       using the SAME evolvable thresholds as the live scanner detector).
    2. Read the playbook forward-settlement trust for the volatility family
       (earned contested record, if any has accrued).
    3. Emit a single candidate-verdict artifact that says exactly what is
       and is not supported - and what evidence is still accruing.

The verdict can be "refused" or "accruing"; it can never promote. Promotion
belongs to the truth layer and forward settlement, as ever. Paper-only.

Usage:  .venv\\Scripts\\python operator_tools\\operator_compression_candidate_pipeline.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dopey.strategy_engineering.compression_expansion_study import (  # noqa: E402
    run_compression_expansion_study,
)
from dopey.strategy_engineering.playbook_settlement import (  # noqa: E402
    PLAYBOOK_TRUST_VERSION,
)
from dopey_research_pipeline.artifact_io import write_json_atomic  # noqa: E402
from dopey_research_pipeline.quality_ledger import reproducibility_hash  # noqa: E402

TRUST_PATH = REPO / "artifacts" / "dopey" / "playbook" / "playbook_family_trust.json"
VERDICT_PATH = (
    REPO / "artifacts" / "dopey" / "strategy_engineering" / "compression_candidate_verdict.json"
)


def _setup_trust(setup_id: str) -> dict[str, object]:
    if not TRUST_PATH.exists():
        return {"trust_status": "no_settlement_history_yet"}
    try:
        trust = json.loads(TRUST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"trust_status": f"unreadable:{error}"}
    observed_version = str(trust.get("playbook_trust_version", ""))
    if observed_version != PLAYBOOK_TRUST_VERSION:
        return {
            "trust_status": "incompatible_trust_version",
            "expected_trust_version": PLAYBOOK_TRUST_VERSION,
            "observed_trust_version": observed_version or "missing",
        }
    bucket = trust.get("per_setup", {}).get(setup_id)
    if not isinstance(bucket, dict):
        return {"trust_status": "unrated_no_settlements_for_setup"}
    return {"trust_status": "present", **bucket}


def run_pipeline() -> dict[str, object]:
    study = run_compression_expansion_study()
    trust = _setup_trust("bb_squeeze_breakout")
    range_survives = bool(
        study["range_question"].get("survives_both_eras_same_sign_above_null")
    )
    direction_supported = bool(
        study["direction_question"].get("directional_claim_supported")
    )
    if direction_supported and range_survives:
        verdict = "historical_support_forward_settlement_must_still_earn_trust"
    elif range_survives:
        verdict = "range_claim_supported_directional_claim_refused"
    else:
        verdict = "no_historical_claim_supported_detections_accrue_as_research_only"
    result = {
        "artifact_type": "compression_candidate_verdict",
        "pipeline_version": "dopey-compression-candidate-pipeline-v1",
        "setup_id": "bb_squeeze_breakout",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "range_question_survives": range_survives,
        "directional_claim_supported": direction_supported,
        "study": {
            "range_question": study["range_question"],
            "direction_question": study["direction_question"],
            "parameters": study["parameters"],
        },
        "forward_settlement_trust": trust,
        "promotion_allowed": False,
        "not_edge_evidence": True,
        "paper_only": True,
        "live_blocked": True,
    }
    result["reproducibility_hash"] = reproducibility_hash(result)
    write_json_atomic(VERDICT_PATH, result)
    return result


def main() -> int:
    result = run_pipeline()
    print(
        json.dumps(
            {
                "verdict": result["verdict"],
                "range_question_survives": result["range_question_survives"],
                "directional_claim_supported": result["directional_claim_supported"],
                "train_events": result["study"]["direction_question"]["train"].get("events"),
                "validation_events": result["study"]["direction_question"]["validation"].get("events"),
                "artifact": str(VERDICT_PATH),
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
