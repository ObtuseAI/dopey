"""dopey_walk_forward — offline deterministic walk-forward replay harness.

Replays fixture-based StrategyGenomes over multiple historical fixture windows, scores
walk-forward consistency, detects overfit/fragility, records results into the ProofLedger, and
feeds summarized results back into the ProofWeightedAggressionGate. Fully offline, paper-only,
and live-blocked: no broker, no credentials, no network, no live order placement.
"""
from .window_model import WalkForwardWindow, load_walk_forward_windows, WALK_FORWARD_DIR
from .replay_models import ReplayResult, WalkForwardScore, OverfitSignal, ReplayVerdict
from .overfit_classifier import classify_overfit
from .scoring import score_walk_forward
from .replay_engine import ReplayEngine, replay_walk_forward
from .aggression_replay import evaluate_replay_promotion
from .ledger_replay import build_replay_proof_entry
from .runner import run_fixture_walk_forward, WalkForwardResult
from .safety_review import safety_review
