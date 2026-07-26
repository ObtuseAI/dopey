# Behavioral Firewall

`dopey/ascendancy/behavioral_firewall.py` advances immutable, strictly chronological
behavioral state. It detects post-loss size and frequency escalation, abstention
override, FOMO, loss-limit drift, ignored invalidation, duplicated events, and active
cooldown. A violation creates a forced cooldown; loss-limit drift or ignored
invalidation also persists quarantine. Automated controls can tighten but never
loosen risk.

The firewall is exercised with mechanics fixtures only. It requires an immutable
prospective decision and override ledger before behavioral effectiveness can be
measured. Shared provenance: `ARTIFACT_PROVENANCE.json`.
