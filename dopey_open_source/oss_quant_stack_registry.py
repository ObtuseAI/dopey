"""Static open-source quant stack candidates. No network, clone, or import."""
from __future__ import annotations

from .oss_models import OSS_STACK_VERSION, OssCandidate


def build_oss_candidate_registry() -> list[OssCandidate]:
    return [
        _candidate("oss-lean", "QuantConnect LEAN", "https://github.com/QuantConnect/Lean", "full algorithmic research/backtesting engines", "Apache-2.0", "review_required", "active", "high", "high", "high", "medium", "medium", 8.5, "reference_only"),
        _candidate("oss-qlib", "Microsoft Qlib", "https://github.com/microsoft/qlib", "ML quant research frameworks", "MIT", "permissive_review_required", "active", "medium", "low", "low", "medium", "low", 8.0, "sandbox_candidate"),
        _candidate("oss-finrl", "FinRL", "https://github.com/AI4Finance-Foundation/FinRL", "RL/agent research frameworks", "MIT", "permissive_review_required", "active", "medium", "medium", "medium", "medium", "low", 7.2, "sandbox_candidate"),
        _candidate("oss-quantlib", "QuantLib", "https://github.com/lballabio/QuantLib", "options pricing/math libraries", "BSD-style", "permissive_review_required", "active", "medium", "low", "low", "low", "low", 9.0, "adapter_candidate"),
        _candidate("oss-backtrader", "backtrader", "https://github.com/mementum/backtrader", "event-loop/backtesting frameworks", "GPL-3.0", "copyleft_manual_review", "stale", "medium", "medium", "medium", "low", "low", 6.0, "reference_only"),
        _candidate("oss-zipline-style", "Zipline-style references", "https://github.com/quantopian/zipline", "event-loop/backtesting frameworks", "Apache-2.0", "review_required", "stale", "high", "medium", "medium", "medium", "low", 5.8, "reference_only"),
        _candidate("oss-vectorbt-style", "vectorbt-style references", "https://github.com/polakowo/vectorbt", "portfolio/risk analytics", "Apache-2.0", "review_required", "active", "medium", "low", "low", "medium", "low", 7.8, "reference_only"),
        _candidate("oss-ta-style", "pandas-ta / ta-style indicators", "https://github.com/twopirllc/pandas-ta", "feature engineering libraries", "mixed_or_unknown", "unknown_manual_review", "unclear", "medium", "low", "low", "low", "low", 6.5, "reference_only"),
        _candidate("oss-yfinance-style", "yfinance-style free data adapter candidates", "https://github.com/ranaroussi/yfinance", "open data adapters", "Apache-2.0", "review_required", "active", "medium", "low", "low", "high", "low", 4.0, "reference_only"),
        _candidate("oss-edgar-tools", "SEC EDGAR open-source tooling candidates", "https://github.com/datasets/sec-edgar", "financial NLP/fundamentals libraries", "review_required", "review_required", "varies", "medium", "low", "low", "medium", "low", 6.7, "reference_only"),
        _candidate("oss-fred-tools", "FRED/open macro tooling candidates", "https://github.com/mortada/fredapi", "open data adapters", "BSD-style", "review_required", "active", "medium", "low", "low", "medium", "medium", 5.0, "reference_only"),
        _candidate("oss-great-expectations", "Great Expectations", "https://github.com/great-expectations/great_expectations", "validation/data-quality tools", "Apache-2.0", "review_required", "active", "high", "low", "low", "medium", "low", 7.0, "reference_only"),
    ]


def oss_candidate_records() -> list[dict]:
    return [candidate.to_dict() for candidate in build_oss_candidate_registry()]


def _candidate(
    candidate_id: str,
    repo_name: str,
    repo_url: str,
    category: str,
    license_name: str,
    license_review_status: str,
    maintenance_status: str,
    dependency_risk: str,
    live_trading_risk: str,
    broker_integration_risk: str,
    network_fetch_risk: str,
    credential_risk: str,
    dopey_value_score: float,
    import_mode: str,
) -> OssCandidate:
    return OssCandidate(
        artifact_type="oss_candidate_registry",
        oss_stack_version=OSS_STACK_VERSION,
        candidate_id=candidate_id,
        repo_name=repo_name,
        repo_url=repo_url,
        category=category,
        license_name=license_name,
        license_review_status=license_review_status,
        maintenance_status=maintenance_status,
        dependency_risk=dependency_risk,
        live_trading_risk=live_trading_risk,
        broker_integration_risk=broker_integration_risk,
        network_fetch_risk=network_fetch_risk,
        credential_risk=credential_risk,
        dopey_value_score=dopey_value_score,
        import_mode=import_mode,
        approval_required=True,
        not_imported=True,
        not_executed=True,
        paper_only=True,
        live_blocked=True,
        candidate_hash="",
    )
