"""Models for exhaustive autonomous open-data discovery."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from dopey_autonomy.autonomy_common import stable_hash


DISCOVERY_VERSION = "dopey-open-data-breakthrough-options-evidence-completion-v1"

ALLOWED_MACHINE_ADMISSIBILITY_STATUSES = frozenset({
    "accepted_machine_verified_open_ohlcv_candidate",
    "accepted_machine_verified_open_options_candidate",
    "accepted_machine_verified_context_candidate",
    "accepted_machine_verified_fixture_only",
    "rejected_unknown_license",
    "rejected_ambiguous_terms",
    "rejected_credentials_required",
    "rejected_login_required",
    "rejected_payment_required",
    "rejected_scrape_only",
    "rejected_broker_or_live_source",
    "rejected_alpha_vantage",
    "rejected_tradingview",
    "rejected_no_bulk_machine_access",
    "quarantined_needs_content_validation",
    "terminal_block",
})


@dataclass(frozen=True)
class ExhaustiveOpenDataCandidate:
    candidate_id: str
    source_name: str
    source_url: str
    discovery_channel: str
    dataset_family: str
    license_name: str
    license_url: str
    license_machine_verified: bool
    terms_url: str
    terms_machine_verified: bool
    requires_credentials: bool
    requires_login: bool
    requires_payment: bool
    requires_scraping: bool
    bulk_download_available: bool
    api_key_required: bool
    historical_depth_claim: str
    asset_coverage_claim: str
    options_data_claim: str
    ohlcv_data_claim: str
    schema_claim: str
    provenance_claim: str
    direct_download_url: str
    machine_admissibility_status: str
    reject_reason: str
    paper_only: bool = True
    live_blocked: bool = True

    def to_dict(self) -> dict[str, Any]:
        if self.machine_admissibility_status not in ALLOWED_MACHINE_ADMISSIBILITY_STATUSES:
            raise ValueError(f"unsupported machine_admissibility_status: {self.machine_admissibility_status}")
        record = asdict(self)
        record["artifact_type"] = "exhaustive_open_data_candidate_registry"
        record["discovery_version"] = DISCOVERY_VERSION
        record["candidate_hash"] = stable_hash(record)
        return record


def is_accepted_status(status: str) -> bool:
    return status.startswith("accepted_machine_verified_")


def is_ohlcv_status(status: str) -> bool:
    return status == "accepted_machine_verified_open_ohlcv_candidate"


def is_options_status(status: str) -> bool:
    return status == "accepted_machine_verified_open_options_candidate"


def is_context_status(status: str) -> bool:
    return status == "accepted_machine_verified_context_candidate"

