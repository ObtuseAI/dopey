# Fill Model Validation

Status: `mechanics_tested_market_untested`.

Automated tests cover quote-content tampering, nonfirm or invalid quotes, contract
and multiplier mismatch, exact leg cardinality, displayed size, later-witness
ordering, entry and cancellation windows, package skew, limit crossing, missed fills,
ticket identity mutation, and the rule that a paper fill is never realized evidence.

No qualifying later-witness stream or realized-fill corpus exists. Fill probability,
queue position, partial fills, package degradation, venue effects, opportunity cost,
market impact, and capacity remain unvalidated and block certification. Shared
provenance: `ARTIFACT_PROVENANCE.json`.
