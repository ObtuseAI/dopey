"""Isolated genome replay over immutable evaluation observations."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Final, TypedDict, cast

from dopey.chronos.replay import ReplayEra, ReplayRole, validate_replay_eras
from dopey.genome.schema import ResearchGenome
from dopey.protocols.identity import canonical_hash
from dopey.truth.causal_evaluation import evaluate_causal_cohorts
from dopey.truth.cohorts import canonicalize_evaluation_records


REPLAY_OBSERVATION_MANIFEST_VERSION: Final[str] = "dopey-replay-observation-manifest-v2"
REPLAY_EVALUATOR_VERSION: Final[str] = "dopey-isolated-genome-replay-v3"
LOCAL_MANIFEST_TRUST_STATUS: Final[str] = "local_untrusted_builder"
LOCAL_ATTESTATION_STATUS: Final[str] = "not_configured"
LOCAL_DATASET_VERIFICATION_STATUS: Final[str] = "caller_asserted_unverified"
LOCAL_PROMOTION_CAP: Final[str] = "SHADOW_ONLY"
SAMPLING_FRAME_BINDING_VERSION: Final[str] = "typed_presence_value_v1"
SAMPLING_FRAME_FIELDS: Final[tuple[str, ...]] = (
    "child_id",
    "strategy_id",
    "setup_family",
    "exit_policy",
    "dte_bucket",
    "moneyness_bucket",
    "direction",
    "regime",
    "symbol",
    "era",
    "held_out",
    "contested_truth",
)


class ReplayObservationManifest(TypedDict):
    artifact_type: str
    manifest_version: str
    candidate_id: str
    genome_id: str
    dataset_id: str
    dataset_content_hash: str
    observation_generator_version: str
    era_set_hash: str
    sampling_frame_hash: str
    observation_set_hash: str
    observation_count: int
    observations: list[dict[str, Any]]
    builder_trust_status: str
    evaluator_attestation_status: str
    evaluator_key_id: str
    evaluator_signature: str
    dataset_snapshot_verification_status: str
    promotion_state_cap: str
    candidate_manifest_authority_granted: bool
    paper_only: bool
    live_blocked: bool
    manifest_hash: str


_MANIFEST_FIELDS: Final[frozenset[str]] = frozenset(
    ReplayObservationManifest.__required_keys__
)
REPLAY_ARTIFACT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "artifact_type",
        "automatic_promotion_allowed",
        "backtest_is_forward_proof",
        "candidate_id",
        "causal_evaluation",
        "causal_input_hash",
        "causal_input_records",
        "dataset_content_hash",
        "dataset_id",
        "dataset_snapshot_verification_status",
        "era_set_hash",
        "era_validation",
        "evaluation_seed",
        "evaluation_spec_hash",
        "evaluator_attestation_status",
        "evaluator_attestation_verified",
        "evaluator_mutable_by_candidate",
        "genome_id",
        "held_out_definition_mutable_by_candidate",
        "live_blocked",
        "observation_count",
        "observation_generator_version",
        "observation_manifest_hash",
        "observation_order_policy",
        "paper_only",
        "promotion_state_cap",
        "randomization_policy",
        "replay_version",
        "reproducibility_hash",
        "sampling_frame_hash",
        "source_data_mutated",
    }
)
CAUSAL_EVALUATION_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "any_cohort_regime_robust",
        "artifact_type",
        "bootstrap_iterations",
        "causal_evaluation_version",
        "circular_shift_count",
        "cohort_count",
        "evaluations",
        "familywise_alpha",
        "human_review_required",
        "live_blocked",
        "minimum_sample",
        "multiple_testing_methods",
        "optimizer_may_tune_evaluator",
        "paper_only",
        "promotion_authority",
        "protected_evaluator",
        "record_count",
        "reproducibility_hash",
        "statistical_truth_promotion_allowed",
    }
)
CAUSAL_COHORT_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "automatic_promotion_allowed",
        "automatic_research_activation_allowed",
        "automatic_research_state_transition_allowed",
        "benjamini_hochberg_adjusted_p_value",
        "bonferroni_adjusted_p_value",
        "bootstrap_mean_gain_ci",
        "causal_confidence",
        "child_attribution_preserved",
        "child_ids",
        "circular_shift_null_mean",
        "circular_shift_null_p_value",
        "cohort_id",
        "cohort_regime_robust",
        "contested_truth_count",
        "contested_truth_gain",
        "era_count",
        "era_transfer_fraction_positive",
        "full_promotion_matrix_required",
        "held_out",
        "human_review_required",
        "noise_adjusted_gain",
        "null_replications",
        "observed_gain",
        "promotion_recommendation",
        "replications",
        "sample_count",
        "symbol_count",
        "symbol_transfer_fraction_positive",
    }
)


def _era_set_hash(eras: tuple[ReplayEra, ...]) -> str:
    return canonical_hash(
        {
            "eras": sorted(
                (era.to_dict() for era in eras),
                key=lambda era: (
                    era["start_date"],
                    era["end_date"],
                    era["era_id"],
                ),
            )
        }
    )


def _validate_digest(value: str, field_name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(
            f"replay observation manifest requires a SHA-256 digest: field={field_name}, value={value}"
        )


def _sampling_frame_field_binding(
    observation: Mapping[str, Any],
    field_name: str,
) -> dict[str, Any]:
    if field_name not in observation:
        return {
            "presence": "missing",
            "value_type": "missing",
        }
    value = observation[field_name]
    if value is None:
        value_type = "null"
    elif isinstance(value, bool):
        value_type = "boolean"
    elif isinstance(value, int):
        value_type = "integer"
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(
                "replay observation sampling-frame values must be finite: "
                f"field={field_name}, value={value}"
            )
        value_type = "number"
    elif isinstance(value, str):
        value_type = "string"
    else:
        raise TypeError(
            "replay observation sampling-frame values must be scalar: "
            f"field={field_name}, actual={type(value).__name__}"
        )
    return {
        "presence": "present",
        "value_type": value_type,
        "value": value,
    }


def _sampling_frame_hash(
    observations: tuple[Mapping[str, Any], ...],
) -> str:
    frame_rows: list[dict[str, Any]] = []
    child_ids: set[str] = set()
    for index, observation in enumerate(observations):
        child_id = observation.get("child_id")
        if not isinstance(child_id, str) or not child_id:
            raise ValueError(
                "replay observation sampling frame requires a stable child ID: "
                f"index={index}"
            )
        if child_id in child_ids:
            raise ValueError(
                "replay observation sampling frame child IDs must be unique: "
                f"child_id={child_id}"
            )
        child_ids.add(child_id)
        frame_rows.append(
            {
                field_name: _sampling_frame_field_binding(observation, field_name)
                for field_name in SAMPLING_FRAME_FIELDS
            }
        )
    return canonical_hash(
        {
            "frame_binding_version": SAMPLING_FRAME_BINDING_VERSION,
            "frame_fields": list(SAMPLING_FRAME_FIELDS),
            "rows": sorted(frame_rows, key=lambda row: str(row["child_id"])),
        }
    )


def build_replay_observation_manifest(
    candidate_id: str,
    genome_id: str,
    eras: tuple[ReplayEra, ...],
    observations: tuple[Mapping[str, Any], ...],
    dataset_id: str,
    dataset_content_hash: str,
    observation_generator_version: str,
) -> ReplayObservationManifest:
    """Bind protected replay observations to immutable evaluation identities."""

    validate_replay_eras(eras)
    required_strings = {
        "candidate_id": candidate_id,
        "genome_id": genome_id,
        "dataset_id": dataset_id,
        "observation_generator_version": observation_generator_version,
    }
    for field_name, value in required_strings.items():
        if not value:
            raise ValueError(
                f"replay observation manifest requires a non-empty identity: field={field_name}"
            )
    _validate_digest(dataset_content_hash, "dataset_content_hash")
    normalized_observations = [dict(observation) for observation in observations]
    sampling_frame_hash = _sampling_frame_hash(observations)
    body: dict[str, Any] = {
        "artifact_type": "protected_replay_observation_manifest",
        "manifest_version": REPLAY_OBSERVATION_MANIFEST_VERSION,
        "candidate_id": candidate_id,
        "genome_id": genome_id,
        "dataset_id": dataset_id,
        "dataset_content_hash": dataset_content_hash,
        "observation_generator_version": observation_generator_version,
        "era_set_hash": _era_set_hash(eras),
        "sampling_frame_hash": sampling_frame_hash,
        "observation_set_hash": canonical_hash(
            {"observations": normalized_observations}
        ),
        "observation_count": len(normalized_observations),
        "observations": normalized_observations,
        "builder_trust_status": LOCAL_MANIFEST_TRUST_STATUS,
        "evaluator_attestation_status": LOCAL_ATTESTATION_STATUS,
        "evaluator_key_id": "",
        "evaluator_signature": "",
        "dataset_snapshot_verification_status": (LOCAL_DATASET_VERIFICATION_STATUS),
        "promotion_state_cap": LOCAL_PROMOTION_CAP,
        "candidate_manifest_authority_granted": False,
        "paper_only": True,
        "live_blocked": True,
    }
    return cast(
        ReplayObservationManifest,
        {**body, "manifest_hash": canonical_hash(body)},
    )


def validate_replay_observation_manifest(
    manifest: Mapping[str, Any],
    candidate_id: str,
    genome_id: str,
    eras: tuple[ReplayEra, ...],
) -> tuple[dict[str, Any], ...]:
    if set(manifest) != _MANIFEST_FIELDS:
        raise ValueError(
            "replay observation manifest differs from the exact schema: "
            f"missing={sorted(_MANIFEST_FIELDS - set(manifest))}, "
            f"unexpected={sorted(set(manifest) - _MANIFEST_FIELDS)}"
        )
    if manifest["artifact_type"] != "protected_replay_observation_manifest":
        raise ValueError("replay observation manifest has an invalid artifact type")
    if manifest["manifest_version"] != REPLAY_OBSERVATION_MANIFEST_VERSION:
        raise ValueError(
            "replay observation manifest version mismatch: "
            f"expected={REPLAY_OBSERVATION_MANIFEST_VERSION}, "
            f"actual={manifest['manifest_version']}"
        )
    if manifest["candidate_id"] != candidate_id:
        raise ValueError(
            "replay observation manifest candidate mismatch: "
            f"expected={candidate_id}, actual={manifest['candidate_id']}"
        )
    if manifest["genome_id"] != genome_id:
        raise ValueError(
            "replay observation manifest genome mismatch: "
            f"expected={genome_id}, actual={manifest['genome_id']}"
        )
    expected_untrusted_fields = {
        "builder_trust_status": LOCAL_MANIFEST_TRUST_STATUS,
        "evaluator_attestation_status": LOCAL_ATTESTATION_STATUS,
        "evaluator_key_id": "",
        "evaluator_signature": "",
        "dataset_snapshot_verification_status": (LOCAL_DATASET_VERIFICATION_STATUS),
        "promotion_state_cap": LOCAL_PROMOTION_CAP,
    }
    for field_name, expected_value in expected_untrusted_fields.items():
        if manifest[field_name] != expected_value:
            raise ValueError(
                "local replay observation manifest cannot self-assert trust: "
                f"field={field_name}, expected={expected_value!r}, "
                f"actual={manifest[field_name]!r}"
            )
    if manifest["candidate_manifest_authority_granted"] is not False:
        raise ValueError(
            "replay observation manifest must deny candidate manifest authority"
        )
    if manifest["paper_only"] is not True or manifest["live_blocked"] is not True:
        raise ValueError(
            "replay observation manifest must preserve paper-only live-blocked scope"
        )
    for field_name in (
        "candidate_id",
        "genome_id",
        "dataset_id",
        "observation_generator_version",
    ):
        if not isinstance(manifest[field_name], str) or not manifest[field_name]:
            raise ValueError(
                f"replay observation manifest requires a non-empty string: field={field_name}"
            )
    if not isinstance(manifest["dataset_content_hash"], str):
        raise TypeError("replay observation manifest dataset hash must be a string")
    dataset_content_hash = manifest["dataset_content_hash"]
    _validate_digest(dataset_content_hash, "dataset_content_hash")
    if not isinstance(manifest["era_set_hash"], str):
        raise TypeError("replay observation manifest era-set hash must be a string")
    _validate_digest(manifest["era_set_hash"], "era_set_hash")
    if manifest["era_set_hash"] != _era_set_hash(eras):
        raise ValueError("replay observation manifest era-set binding mismatch")
    raw_observations = manifest["observations"]
    if not isinstance(raw_observations, list) or any(
        not isinstance(observation, Mapping) for observation in raw_observations
    ):
        raise TypeError("replay observation manifest requires an object array")
    observations = tuple(dict(observation) for observation in raw_observations)
    if not isinstance(manifest["sampling_frame_hash"], str):
        raise TypeError(
            "replay observation manifest sampling-frame hash must be a string"
        )
    _validate_digest(manifest["sampling_frame_hash"], "sampling_frame_hash")
    expected_sampling_frame_hash = _sampling_frame_hash(observations)
    if manifest["sampling_frame_hash"] != expected_sampling_frame_hash:
        raise ValueError("replay observation manifest sampling-frame hash mismatch")
    if not isinstance(manifest["observation_count"], int) or isinstance(
        manifest["observation_count"],
        bool,
    ):
        raise TypeError("replay observation manifest count must be an integer")
    if manifest["observation_count"] != len(observations):
        raise ValueError(
            "replay observation manifest count mismatch: "
            f"declared={manifest['observation_count']}, actual={len(observations)}"
        )
    expected_observation_hash = canonical_hash({"observations": list(observations)})
    if not isinstance(manifest["observation_set_hash"], str):
        raise TypeError("replay observation manifest observation hash must be a string")
    _validate_digest(manifest["observation_set_hash"], "observation_set_hash")
    if manifest["observation_set_hash"] != expected_observation_hash:
        raise ValueError("replay observation manifest observation hash mismatch")
    body = {
        str(key): value for key, value in manifest.items() if key != "manifest_hash"
    }
    if not isinstance(manifest["manifest_hash"], str):
        raise TypeError("replay observation manifest content hash must be a string")
    _validate_digest(manifest["manifest_hash"], "manifest_hash")
    if manifest["manifest_hash"] != canonical_hash(body):
        raise ValueError("replay observation manifest content hash mismatch")
    return observations


def _require_integer(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(
            f"causal evaluation field must be an integer: field={field_name}"
        )
    return value


def _require_finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"causal evaluation field must be numeric: field={field_name}")
    normalized = float(value)
    if not math.isfinite(normalized):
        raise ValueError(
            f"causal evaluation field must be finite: field={field_name}, value={value}"
        )
    return normalized


def _require_fraction(value: Any, field_name: str) -> float:
    normalized = _require_finite_number(value, field_name)
    if not 0.0 <= normalized <= 1.0:
        raise ValueError(
            "causal evaluation fraction must be within [0, 1]: "
            f"field={field_name}, value={normalized}"
        )
    return normalized


def _expected_bh_adjustments(raw: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(raw.items(), key=lambda item: (item[1], item[0]))
    adjusted: dict[str, float] = {}
    running = 1.0
    for reverse_index in range(len(ordered) - 1, -1, -1):
        cohort_id, probability = ordered[reverse_index]
        rank = reverse_index + 1
        running = min(running, probability * len(ordered) / rank)
        adjusted[cohort_id] = min(1.0, running)
    return adjusted


def _validate_causal_cohort(
    record: Mapping[str, Any],
    cohort_count: int,
    bootstrap_iterations: int,
    circular_shift_count: int,
    familywise_alpha: float,
    minimum_sample: int,
) -> tuple[str, int, bool, float, tuple[str, ...]]:
    if set(record) != CAUSAL_COHORT_FIELDS:
        raise ValueError(
            "causal cohort evaluation differs from the exact schema: "
            f"missing={sorted(CAUSAL_COHORT_FIELDS - set(record))}, "
            f"unexpected={sorted(set(record) - CAUSAL_COHORT_FIELDS)}"
        )
    cohort_id = record["cohort_id"]
    if not isinstance(cohort_id, str) or not cohort_id:
        raise ValueError("causal cohort evaluation requires a non-empty cohort ID")
    expected_constants = {
        "automatic_research_state_transition_allowed": True,
        "automatic_research_activation_allowed": False,
        "automatic_promotion_allowed": False,
        "full_promotion_matrix_required": True,
        "human_review_required": False,
        "child_attribution_preserved": True,
    }
    for field_name, expected_value in expected_constants.items():
        if record[field_name] is not expected_value:
            raise ValueError(
                "causal cohort evaluation violates its protected boundary: "
                f"field={field_name}, expected={expected_value!r}, "
                f"actual={record[field_name]!r}"
            )
    sample_count = _require_integer(record["sample_count"], "sample_count")
    if sample_count <= 0:
        raise ValueError("causal cohort evaluation sample count must be positive")
    child_ids = record["child_ids"]
    if (
        not isinstance(child_ids, list)
        or any(not isinstance(child_id, str) or not child_id for child_id in child_ids)
        or child_ids != sorted(child_ids)
        or len(child_ids) != len(set(child_ids))
        or len(child_ids) != sample_count
    ):
        raise ValueError(
            "causal cohort evaluation child IDs must be unique, sorted, and match sample count"
        )
    replications = _require_integer(record["replications"], "replications")
    if replications != bootstrap_iterations:
        raise ValueError(
            "causal cohort evaluation bootstrap replication count mismatch"
        )
    null_replications = _require_integer(
        record["null_replications"],
        "null_replications",
    )
    expected_null_replications = (
        min(circular_shift_count, sample_count - 1) if sample_count >= 2 else 0
    )
    if null_replications != expected_null_replications:
        raise ValueError("causal cohort evaluation null replication count mismatch")
    symbol_count = _require_integer(record["symbol_count"], "symbol_count")
    era_count = _require_integer(record["era_count"], "era_count")
    contested_truth_count = _require_integer(
        record["contested_truth_count"],
        "contested_truth_count",
    )
    if not 1 <= symbol_count <= sample_count:
        raise ValueError("causal cohort evaluation symbol count is invalid")
    if not 1 <= era_count <= sample_count:
        raise ValueError("causal cohort evaluation era count is invalid")
    if not 0 <= contested_truth_count <= sample_count:
        raise ValueError("causal cohort evaluation contested-truth count is invalid")
    if not isinstance(record["held_out"], bool):
        raise TypeError("causal cohort evaluation held-out status must be boolean")
    if not isinstance(record["cohort_regime_robust"], bool):
        raise TypeError("causal cohort evaluation robust status must be boolean")
    for field_name in (
        "observed_gain",
        "noise_adjusted_gain",
        "circular_shift_null_mean",
    ):
        _require_finite_number(record[field_name], field_name)
    interval = record["bootstrap_mean_gain_ci"]
    if not isinstance(interval, list) or len(interval) != 2:
        raise ValueError("causal cohort evaluation requires a two-value interval")
    interval_lower = _require_finite_number(
        interval[0],
        "bootstrap_mean_gain_ci[0]",
    )
    interval_upper = _require_finite_number(
        interval[1],
        "bootstrap_mean_gain_ci[1]",
    )
    if interval_lower > interval_upper:
        raise ValueError("causal cohort evaluation interval is reversed")
    raw_probability = _require_fraction(
        record["circular_shift_null_p_value"],
        "circular_shift_null_p_value",
    )
    bonferroni = _require_fraction(
        record["bonferroni_adjusted_p_value"],
        "bonferroni_adjusted_p_value",
    )
    _require_fraction(
        record["benjamini_hochberg_adjusted_p_value"],
        "benjamini_hochberg_adjusted_p_value",
    )
    symbol_transfer = _require_fraction(
        record["symbol_transfer_fraction_positive"],
        "symbol_transfer_fraction_positive",
    )
    era_transfer = _require_fraction(
        record["era_transfer_fraction_positive"],
        "era_transfer_fraction_positive",
    )
    causal_confidence = _require_fraction(
        record["causal_confidence"],
        "causal_confidence",
    )
    expected_bonferroni = round(
        min(1.0, raw_probability * max(cohort_count, 1)),
        8,
    )
    if bonferroni != expected_bonferroni:
        raise ValueError("causal cohort evaluation Bonferroni value mismatch")
    contested_truth_gain_value = record["contested_truth_gain"]
    if contested_truth_gain_value is None:
        if contested_truth_count != 0:
            raise ValueError(
                "causal cohort evaluation contested gain is missing for contested rows"
            )
        contested_truth_gain: float | None = None
    else:
        contested_truth_gain = _require_finite_number(
            contested_truth_gain_value,
            "contested_truth_gain",
        )
        if contested_truth_count == 0:
            raise ValueError(
                "causal cohort evaluation contested gain exists without contested rows"
            )
    expected_robust = (
        sample_count >= minimum_sample
        and interval_lower > 0.0
        and bonferroni <= familywise_alpha
        and record["held_out"] is True
        and symbol_count >= 3
        and era_count >= 2
        and symbol_transfer >= 2.0 / 3.0
        and era_transfer >= 2.0 / 3.0
        and (contested_truth_gain is None or contested_truth_gain >= 0.0)
    )
    if record["cohort_regime_robust"] is not expected_robust:
        raise ValueError("causal cohort evaluation robust-state invariant mismatch")
    expected_recommendation = "HELD_OUT_VALIDATED" if expected_robust else "SHADOW_ONLY"
    if record["promotion_recommendation"] != expected_recommendation:
        raise ValueError("causal cohort evaluation recommendation invariant mismatch")
    expected_confidence = round(
        min(
            1.0,
            (sample_count / minimum_sample)
            * max(0.0, 1.0 - bonferroni)
            * symbol_transfer
            * era_transfer,
        ),
        8,
    )
    if causal_confidence != expected_confidence:
        raise ValueError("causal cohort evaluation confidence invariant mismatch")
    return (
        cohort_id,
        sample_count,
        expected_robust,
        raw_probability,
        tuple(child_ids),
    )


def _validate_causal_evaluation(
    causal_evaluation: Mapping[str, Any],
    expected_record_count: int,
) -> None:
    if set(causal_evaluation) != CAUSAL_EVALUATION_FIELDS:
        raise ValueError(
            "causal evaluation differs from the exact schema: "
            f"missing={sorted(CAUSAL_EVALUATION_FIELDS - set(causal_evaluation))}, "
            f"unexpected={sorted(set(causal_evaluation) - CAUSAL_EVALUATION_FIELDS)}"
        )
    reproducibility_hash = causal_evaluation["reproducibility_hash"]
    if not isinstance(reproducibility_hash, str):
        raise TypeError("causal evaluation reproducibility hash must be a string")
    _validate_digest(reproducibility_hash, "causal_evaluation.reproducibility_hash")
    body = {
        str(key): value
        for key, value in causal_evaluation.items()
        if key != "reproducibility_hash"
    }
    if reproducibility_hash != canonical_hash(body):
        raise ValueError("causal evaluation reproducibility hash mismatch")
    expected_constants = {
        "artifact_type": "vnext_causal_cohort_evaluation",
        "causal_evaluation_version": "dopey-causal-evaluation-v1",
        "protected_evaluator": True,
        "optimizer_may_tune_evaluator": False,
        "multiple_testing_methods": ["bonferroni", "benjamini_hochberg"],
        "statistical_truth_promotion_allowed": False,
        "promotion_authority": "protected_symbol_strategy_pair_threshold_matrix",
        "human_review_required": False,
        "paper_only": True,
        "live_blocked": True,
    }
    for field_name, expected_value in expected_constants.items():
        if causal_evaluation[field_name] != expected_value:
            raise ValueError(
                "causal evaluation violates its protected boundary: "
                f"field={field_name}, expected={expected_value!r}, "
                f"actual={causal_evaluation[field_name]!r}"
            )
    record_count = _require_integer(
        causal_evaluation["record_count"],
        "record_count",
    )
    if record_count < 0 or record_count != expected_record_count:
        raise ValueError("causal evaluation record count mismatch")
    cohort_count = _require_integer(
        causal_evaluation["cohort_count"],
        "cohort_count",
    )
    if cohort_count < 0:
        raise ValueError("causal evaluation cohort count must be non-negative")
    bootstrap_iterations = _require_integer(
        causal_evaluation["bootstrap_iterations"],
        "bootstrap_iterations",
    )
    if bootstrap_iterations <= 0:
        raise ValueError("causal evaluation bootstrap iterations must be positive")
    circular_shift_count = _require_integer(
        causal_evaluation["circular_shift_count"],
        "circular_shift_count",
    )
    if circular_shift_count < 0:
        raise ValueError("causal evaluation circular-shift count must be non-negative")
    familywise_alpha = _require_finite_number(
        causal_evaluation["familywise_alpha"],
        "familywise_alpha",
    )
    if not 0.0 < familywise_alpha < 1.0:
        raise ValueError("causal evaluation familywise alpha must be within (0, 1)")
    minimum_sample = _require_integer(
        causal_evaluation["minimum_sample"],
        "minimum_sample",
    )
    if minimum_sample <= 0:
        raise ValueError("causal evaluation minimum sample must be positive")
    evaluations = causal_evaluation["evaluations"]
    if not isinstance(evaluations, list) or any(
        not isinstance(record, Mapping) for record in evaluations
    ):
        raise TypeError("causal evaluation requires an object array")
    if cohort_count != len(evaluations):
        raise ValueError("causal evaluation cohort count mismatch")
    validated = [
        _validate_causal_cohort(
            record,
            cohort_count,
            bootstrap_iterations,
            circular_shift_count,
            familywise_alpha,
            minimum_sample,
        )
        for record in evaluations
    ]
    cohort_ids = [record[0] for record in validated]
    if cohort_ids != sorted(cohort_ids) or len(cohort_ids) != len(set(cohort_ids)):
        raise ValueError("causal evaluation cohort IDs must be unique and sorted")
    observed_child_ids = [child_id for record in validated for child_id in record[4]]
    if len(observed_child_ids) != len(set(observed_child_ids)):
        raise ValueError("causal evaluation child IDs overlap across cohorts")
    if sum(record[1] for record in validated) != record_count:
        raise ValueError("causal evaluation cohort samples do not partition records")
    expected_any_robust = any(record[2] for record in validated)
    if causal_evaluation["any_cohort_regime_robust"] is not expected_any_robust:
        raise ValueError("causal evaluation aggregate robust-state invariant mismatch")
    raw_probabilities = {record[0]: record[3] for record in validated}
    expected_bh = _expected_bh_adjustments(raw_probabilities)
    for record in evaluations:
        cohort_id = str(record["cohort_id"])
        observed_bh = _require_fraction(
            record["benjamini_hochberg_adjusted_p_value"],
            "benjamini_hochberg_adjusted_p_value",
        )
        if observed_bh != round(expected_bh[cohort_id], 8):
            raise ValueError(
                "causal cohort evaluation Benjamini-Hochberg value mismatch"
            )


def validate_replay_artifact(
    replay: Mapping[str, Any],
    candidate_id: str,
    genome_id: str,
) -> None:
    if set(replay) != REPLAY_ARTIFACT_FIELDS:
        raise ValueError(
            "isolated replay artifact differs from the exact schema: "
            f"missing={sorted(REPLAY_ARTIFACT_FIELDS - set(replay))}, "
            f"unexpected={sorted(set(replay) - REPLAY_ARTIFACT_FIELDS)}"
        )
    expected_constants = {
        "artifact_type": "isolated_research_genome_replay",
        "replay_version": REPLAY_EVALUATOR_VERSION,
        "candidate_id": candidate_id,
        "genome_id": genome_id,
        "observation_order_policy": "stable_child_id_ascending_v1",
        "evaluator_attestation_verified": False,
        "evaluator_attestation_status": LOCAL_ATTESTATION_STATUS,
        "dataset_snapshot_verification_status": (LOCAL_DATASET_VERIFICATION_STATUS),
        "promotion_state_cap": LOCAL_PROMOTION_CAP,
        "source_data_mutated": False,
        "held_out_definition_mutable_by_candidate": False,
        "evaluator_mutable_by_candidate": False,
        "backtest_is_forward_proof": False,
        "automatic_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    for field_name, expected_value in expected_constants.items():
        if replay[field_name] != expected_value:
            raise ValueError(
                "isolated replay artifact violates its protected boundary: "
                f"field={field_name}, expected={expected_value!r}, "
                f"actual={replay[field_name]!r}"
            )
    for field_name in (
        "observation_manifest_hash",
        "dataset_content_hash",
        "era_set_hash",
        "sampling_frame_hash",
        "evaluation_spec_hash",
        "causal_input_hash",
        "reproducibility_hash",
    ):
        value = replay[field_name]
        if not isinstance(value, str):
            raise TypeError(
                f"isolated replay digest must be a string: field={field_name}"
            )
        _validate_digest(value, field_name)
    if not isinstance(replay["evaluation_seed"], int) or isinstance(
        replay["evaluation_seed"],
        bool,
    ):
        raise TypeError("isolated replay evaluation seed must be an integer")
    observation_count = _require_integer(
        replay["observation_count"],
        "observation_count",
    )
    if observation_count < 0:
        raise ValueError("isolated replay observation count must be non-negative")
    raw_causal_inputs = replay["causal_input_records"]
    if not isinstance(raw_causal_inputs, list) or any(
        not isinstance(record, Mapping) for record in raw_causal_inputs
    ):
        raise TypeError("isolated replay causal inputs must be an object array")
    causal_inputs = [dict(record) for record in raw_causal_inputs]
    if len(causal_inputs) != observation_count:
        raise ValueError("isolated replay causal-input count mismatch")
    child_ids = [str(record.get("child_id", "")) for record in causal_inputs]
    if (
        any(not child_id for child_id in child_ids)
        or child_ids != sorted(child_ids)
        or len(child_ids) != len(set(child_ids))
    ):
        raise ValueError(
            "isolated replay causal inputs require unique child IDs in canonical order"
        )
    expected_causal_input_hash = canonical_hash({"records": causal_inputs})
    if replay["causal_input_hash"] != expected_causal_input_hash:
        raise ValueError("isolated replay causal-input hash mismatch")
    recanonicalized_inputs = canonicalize_evaluation_records(causal_inputs)
    if recanonicalized_inputs != causal_inputs:
        raise ValueError("isolated replay causal inputs are not canonically derived")
    causal_evaluation = replay["causal_evaluation"]
    if not isinstance(causal_evaluation, Mapping):
        raise TypeError("isolated replay causal evaluation must be an object")
    _validate_causal_evaluation(causal_evaluation, observation_count)
    expected_causal_evaluation = evaluate_causal_cohorts(
        causal_inputs,
        _require_integer(
            causal_evaluation["bootstrap_iterations"],
            "bootstrap_iterations",
        ),
        replay["evaluation_seed"],
        _require_integer(
            causal_evaluation["circular_shift_count"],
            "circular_shift_count",
        ),
        _require_finite_number(
            causal_evaluation["familywise_alpha"],
            "familywise_alpha",
        ),
        _require_integer(
            causal_evaluation["minimum_sample"],
            "minimum_sample",
        ),
    )
    if dict(causal_evaluation) != expected_causal_evaluation:
        raise ValueError(
            "isolated replay causal evaluation does not recompute from bound inputs"
        )
    body = {
        str(key): value
        for key, value in replay.items()
        if key != "reproducibility_hash"
    }
    if replay["reproducibility_hash"] != canonical_hash(body):
        raise ValueError("isolated replay artifact reproducibility hash mismatch")


def run_isolated_replay(
    genome: ResearchGenome,
    candidate_id: str,
    eras: tuple[ReplayEra, ...],
    observation_manifest: Mapping[str, Any],
    evaluation_spec_hash: str,
    randomization_policy: str,
    bootstrap_iterations: int,
    seed: int,
    null_shifts: int,
    familywise_alpha: float,
    minimum_sample: int,
) -> dict[str, Any]:
    _validate_digest(evaluation_spec_hash, "evaluation_spec_hash")
    if not randomization_policy:
        raise ValueError("isolated replay requires a randomization policy")
    era_validation = validate_replay_eras(eras)
    observations = validate_replay_observation_manifest(
        observation_manifest,
        candidate_id,
        genome.genome_id,
        eras,
    )
    era_by_id = {era.era_id: era for era in eras}
    ordered_observations = tuple(
        sorted(observations, key=lambda observation: str(observation["child_id"]))
    )
    normalized: list[dict[str, Any]] = []
    for index, observation in enumerate(ordered_observations):
        era_id = str(observation.get("era", ""))
        if era_id not in era_by_id:
            raise ValueError(
                f"replay observation references unknown era: index={index}, era={era_id}"
            )
        role = era_by_id[era_id].role
        declared_held_out = bool(observation.get("held_out", False))
        actual_held_out = role is ReplayRole.HELD_OUT
        if declared_held_out != actual_held_out:
            raise ValueError(
                "replay held-out declaration conflicts with sealed era: "
                f"index={index}, era={era_id}, declared={declared_held_out}, actual={actual_held_out}"
            )
        normalized.append(
            {
                **dict(observation),
                "contested_truth": bool(
                    observation.get("contested_truth", False)
                    or role is ReplayRole.CONTESTED_TRUTH
                ),
            }
        )
    canonical = canonicalize_evaluation_records(normalized)
    causal = evaluate_causal_cohorts(
        canonical,
        bootstrap_iterations,
        seed,
        null_shifts,
        familywise_alpha,
        minimum_sample,
    )
    body: dict[str, Any] = {
        "artifact_type": "isolated_research_genome_replay",
        "replay_version": REPLAY_EVALUATOR_VERSION,
        "candidate_id": candidate_id,
        "genome_id": genome.genome_id,
        "observation_manifest_hash": str(observation_manifest["manifest_hash"]),
        "dataset_id": str(observation_manifest["dataset_id"]),
        "dataset_content_hash": str(observation_manifest["dataset_content_hash"]),
        "observation_generator_version": str(
            observation_manifest["observation_generator_version"]
        ),
        "era_set_hash": str(observation_manifest["era_set_hash"]),
        "sampling_frame_hash": str(observation_manifest["sampling_frame_hash"]),
        "evaluation_spec_hash": evaluation_spec_hash,
        "evaluation_seed": seed,
        "randomization_policy": randomization_policy,
        "evaluator_attestation_verified": False,
        "evaluator_attestation_status": str(
            observation_manifest["evaluator_attestation_status"]
        ),
        "dataset_snapshot_verification_status": str(
            observation_manifest["dataset_snapshot_verification_status"]
        ),
        "promotion_state_cap": str(observation_manifest["promotion_state_cap"]),
        "observation_order_policy": "stable_child_id_ascending_v1",
        "era_validation": era_validation,
        "observation_count": len(ordered_observations),
        "causal_input_hash": canonical_hash({"records": canonical}),
        "causal_input_records": canonical,
        "causal_evaluation": causal,
        "source_data_mutated": False,
        "held_out_definition_mutable_by_candidate": False,
        "evaluator_mutable_by_candidate": False,
        "backtest_is_forward_proof": False,
        "automatic_promotion_allowed": False,
        "paper_only": True,
        "live_blocked": True,
    }
    result = {**body, "reproducibility_hash": canonical_hash(body)}
    validate_replay_artifact(result, candidate_id, genome.genome_id)
    return result
