"""dopey_research_pipeline — offline, deterministic, paper-only research pipeline.

This is the first executable Dopey loop: it takes a fixture option chain, ranks/selects a paper
candidate, generates a paper execution intent, validates it, simulates a PaperBroker fill, logs
execution quality, and appends a structured proof/outcome record to the ProofLedger. It is
fully offline and live-blocked: no broker connection, no credentials, no live order placement.
"""
from .fixtures import load_fixture_chain, FIXTURE_CHAIN_PATH
from .pipeline import run_pipeline, PipelineResult
