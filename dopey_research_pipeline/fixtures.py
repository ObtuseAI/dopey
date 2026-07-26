"""Dopey fixture chain loader: deterministic offline option-chain fixture.

DOPEY-native. Loads the SPY_FIXTURE chain from a local JSON file. No network calls, no
real-time dependency. Returns an OptionChain (dopey_options.ontology) built from the fixture.
"""
from __future__ import annotations

import json
from pathlib import Path

from dopey_options.ontology import OptionChain, OptionContract, Underlying

FIXTURE_CHAIN_PATH = Path(__file__).resolve().parent.parent / "dopey_data" / "fixtures" / "spy_fixture_chain.json"


def load_fixture_chain(path: Path | str | None = None) -> OptionChain:
    """Load the fixture option chain from JSON. Deterministic; no network."""
    p = Path(path) if path else FIXTURE_CHAIN_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    underlying = Underlying.from_dict(data["underlying"])
    contracts = [OptionContract.from_dict(c) for c in data["contracts"]]
    return OptionChain(underlying=underlying, contracts=contracts, as_of=data.get("as_of", ""))


def fixture_symbol_set(chain: OptionChain) -> set[str]:
    """Return the set of option-contract symbols in the fixture chain (for validator checks)."""
    return {c.symbol for c in chain.contracts}
