"""Governed reverse- and forward-engineering laboratories for paper research."""

from .forward import (
    build_evaluation_manifest,
    build_quality_diversity_archive,
    generate_forward_candidates,
)
from .factor_language import build_factor_program, evaluate_factor_program
from .institutional_intelligence import (
    allocate_research_gap_portfolio,
    institutional_evaluation_contract,
    synthesize_institutional_council,
)
from .institutional_registry import (
    INSTITUTIONAL_DOCTRINES,
    INSTITUTIONAL_SOURCES,
    doctrine_by_id,
    validate_institutional_registry,
)
from .institutional_runtime import run_institutional_intelligence_cycle
from .option_roi_discovery import (
    build_option_reverse_cases,
    compute_contract_roi,
    discover_option_roi_strategies,
    load_chain_snapshots,
)
from .lane_context import load_lane_context
from .playbook import (
    PLAYBOOK,
    computable_setups,
    data_gapped_setups,
    playbook_by_family,
    playbook_summary,
)
from .playbook_scanner import SCANNER_EVOLVABLE_PARAMETERS, scan_playbook
from .playbook_settlement import (
    family_trust_report,
    is_rating_eligible_settlement,
    record_detections,
    settle_matured,
    uses_legacy_direction_assumption,
    uses_legacy_dual_framing,
)
from .run_playbook_research_stage import run_playbook_research_stage
from .reverse import build_reverse_cases, infer_reverse_hypotheses
from .runtime import run_strategy_engineering_cycle
from .swing_target_discovery import (
    compute_mover_metrics,
    discover_swing_targets,
    load_ohlcv_history,
    rank_symbol_movers,
)

__all__ = [
    "PLAYBOOK",
    "SCANNER_EVOLVABLE_PARAMETERS",
    "build_evaluation_manifest",
    "build_factor_program",
    "build_option_reverse_cases",
    "build_quality_diversity_archive",
    "build_reverse_cases",
    "computable_setups",
    "compute_contract_roi",
    "compute_mover_metrics",
    "allocate_research_gap_portfolio",
    "data_gapped_setups",
    "discover_option_roi_strategies",
    "discover_swing_targets",
    "generate_forward_candidates",
    "evaluate_factor_program",
    "family_trust_report",
    "is_rating_eligible_settlement",
    "infer_reverse_hypotheses",
    "institutional_evaluation_contract",
    "load_chain_snapshots",
    "load_lane_context",
    "load_ohlcv_history",
    "rank_symbol_movers",
    "playbook_by_family",
    "playbook_summary",
    "record_detections",
    "run_playbook_research_stage",
    "run_institutional_intelligence_cycle",
    "run_strategy_engineering_cycle",
    "scan_playbook",
    "settle_matured",
    "uses_legacy_direction_assumption",
    "uses_legacy_dual_framing",
    "synthesize_institutional_council",
    "doctrine_by_id",
    "validate_institutional_registry",
    "INSTITUTIONAL_DOCTRINES",
    "INSTITUTIONAL_SOURCES",
]
