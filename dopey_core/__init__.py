"""dopey_core — the Dopey Recursive Work Engine (forked from Blunder, renamed).

Loop:  intake -> plan -> mock trial -> execute -> validate -> repair -> ledger -> learn -> (repeat).

This package is a forked-and-renamed copy of the Blunder Recursive Work Engine V1. It is
intentionally stdlib-only and side-effect-sandboxed: real execution writes only inside a per-run
work directory, and nothing risky/irreversible/external runs without an explicit human gate.

DOPEY adds a hard trading boundary on top of Blunder's safety model: no live trade placement,
no funded broker connection, and no Robinhood private API usage in the first pass. See
DOPEY_BROKER_BOUNDARIES.md and DOPEY_RISK_DISCIPLINE.md.
"""
from ._kernel import (  # noqa: F401
    DOPEY_VERSION,
    BLUNDER_LINEAGE_VERSION,
    FinalStatus,
    MockResult,
    ValidationResult,
    RiskLevel,
    TaskType,
    WorkPacket,
    classify_action,
    intake,
    sha256_text,
    sha256_obj,
)
from .proof_ledger import ProofEntry, ProofLedger  # noqa: F401
from .autonomy_loop import Task, make_plan, run  # noqa: F401
from .promotion_gate import evaluate_lessons  # noqa: F401
from .validator_mesh import (  # noqa: F401
    validate_against_schema,
    validate_schema_instance_pair,
    parse_proof_ledger,
    parse_command_trace,
    decode_artifact_name,
    analyze_python_source,
    sweep,
)
from .rollback_manager import (  # noqa: F401
    MAX_REPAIR_ATTEMPTS,
    should_repair,
    run_bounded_repair,
    containment_note,
)
from .adaptive_threshold_kernel import (  # noqa: F401
    inspect_engine,
    weak_module_scan,
    self_operation_readiness,
)
from .replay_engine import (  # noqa: F401
    benchmark_task_packet_schema,
    validate_packets,
    mock_benchmark_trial,
    benchmark_readiness_report,
    replay_fixture_builder,
)
from .mutation_engine import (  # noqa: F401
    mutate_field,
    mutate_genome,
    genome_hash,
    mutation_recommendation,
)
from .config import load_config, default_config_path  # noqa: F401
