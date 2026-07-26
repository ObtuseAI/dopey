"""dopey_oss_miner — OSS source discovery / quarantine / license-gate (forked from Blunder inflow).

This package is a forked-and-renamed copy of the Blunder inflow mesh (the OSS-mining /
source-trust / quarantine / license-gate concepts). Raw inflow never promotes directly; every
candidate is quarantined, risk-scanned, license-scanned, and must pass replay before any
promotion. DOPEY adds a research-only boundary: no uncontrolled web scraping, no credential
exfiltration, and no live trade placement.
"""
from ._models import (  # noqa: F401
    CLASSIFICATION,
    TERMINAL_TARGET,
    SourceCandidate,
    DopeyInflowRecord,
    Paopvol,
    utc_now,
    stable_id,
    empty_paopvol,
    build_record,
)
from .license_scanner import (  # noqa: F401
    COMPATIBLE_LICENSES,
    classify_license,
    license_score,
    is_license_compatible,
)
from .source_value_ranker import (  # noqa: F401
    compute_trust_score,
    compute_risk_score,
    compute_priority,
)
from .repo_discovery import (  # noqa: F401
    build_candidate,
    build_source_registry,
    write_source_registry,
)
from .import_sandbox import quarantine_source  # noqa: F401
from .benchmark_extractor import mine_proof_artifact  # noqa: F401
from .promotion_recommender import evaluate_promotion  # noqa: F401
