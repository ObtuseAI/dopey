# Strategy Retirement Policy

`dopey/ascendancy/retirement.py` returns only `CONTINUE_PAPER`, `QUARANTINED`, or
`RETIRED`. Protected-manifest failure, drawdown beyond the failure envelope,
specification divergence, edge below complete costs, or broken liquidity policy
retires immediately. Calibration, execution, or settlement degradation quarantines
pending review.

Certification is versioned and temporary. A repaired strategy becomes a new
candidate and inherits no approval. No strategy currently exists to monitor or
retire. Shared provenance: `ARTIFACT_PROVENANCE.json`.
