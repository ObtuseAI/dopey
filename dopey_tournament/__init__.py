"""dopey_tournament — offline deterministic multi-strategy paper tournament.

Extends the walk-forward replay harness to run multiple StrategyGenome candidates across the
same deterministic fixture windows, computes S-tier analysis fusion (macro/microstructure/
technical/fundamental/pattern) per window, ranks candidates by combined walk-forward +
analysis-fusion score, records a champion registry, and feeds summary into the
ProofWeightedAggressionGate. Fully offline, paper-only, fixture-based, deterministic,
live-blocked: no broker, no credentials, no network, no live promotion.
"""
from .genome_set import build_tournament_genomes
from .models import TournamentResult, StrategyTournamentScore, ChampionRegistryEntry
from .aggression_tournament import evaluate_tournament_promotion
from .ledger_tournament import build_tournament_proof_entry, write_champion_registry
from .runner import run_fixture_tournament, TournamentSummary
from .run_fixture_tournament import main
