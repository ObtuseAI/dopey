# Greek Risk Framework

Candidate plus portfolio delta, gamma, theta, vega, vanna, charm, vomma, skew,
correlation, event, liquidity, and gap exposures must be finite and remain within the
frozen environment caps. Position loss, margin, expected shortfall, ruin probability,
daily loss, drawdown, and 0DTE are conjunctive gates. The ticket builder rejects
caller-defined risk limits and requires the exact v1 policy and price-derived maximum
loss and DTE.

The gate verifies supplied measurements; it does not prove that a Greek or tail model
is correct. Current legacy European Black-Scholes, dividend, borrow, early-exercise,
assignment, and higher-Greek capabilities do not meet the lifecycle standard. Any
unavailable critical measurement must be non-finite and therefore forces abstention.

Shared provenance: `ARTIFACT_PROVENANCE.json`.
