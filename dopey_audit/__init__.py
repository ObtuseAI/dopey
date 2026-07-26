"""DOPEY offline evidence replay audit harness — deterministic, offline, paper-only.

Audits DOPEY's proof chain (ProofLedger + registries) for reproducibility, internal
consistency, determinism, and safety-boundary drift. Never enables live trading, never
connects to a broker, never uses network access.
"""
