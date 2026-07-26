"""Dopey walk-forward window model + loader (offline, deterministic).

A WalkForwardWindow is a serializable fixture window carrying an underlying snapshot, an
option-chain snapshot, a deterministic next-step outcome, a regime tag, and liquidity/spread
fields. Loaded from JSON fixtures under dopey_data/fixtures/walk_forward/. No network.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

from dopey_options.ontology import OptionChain, OptionContract, Underlying

WALK_FORWARD_DIR = Path(__file__).resolve().parent.parent / "dopey_data" / "fixtures" / "walk_forward"


@dataclass
class WalkForwardWindow:
    window_id: str
    window_type: str            # train | validation | holdout
    timestamp: str
    regime_tag: str
    underlying_snapshot: dict
    option_chain: OptionChain
    expected_outcome: dict
    notes: str = ""
    sequence_id: int = 0
    # Restored fields (lost in the branch-switch file loss; the corpus fixtures
    # carry them at top level and the tournament/consistency runners consume
    # them): per-family outcome hints and the regime liquidity/penalty context.
    family_outcome_hints: dict = field(default_factory=dict)
    regime_context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["option_chain"] = self.option_chain.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "WalkForwardWindow":
        return cls(
            window_id=d["window_id"],
            window_type=d["window_type"],
            timestamp=d["timestamp"],
            regime_tag=d["regime_tag"],
            underlying_snapshot=d["underlying_snapshot"],
            option_chain=OptionChain.from_dict(d["option_chain"]),
            expected_outcome=d["expected_outcome"],
            notes=d.get("notes", ""),
            sequence_id=d.get("sequence_id", 0),
            family_outcome_hints=d.get("family_outcome_hints", {}),
            regime_context=d.get("regime_context", {}),
        )

    def chain_symbols(self) -> set[str]:
        return {c.symbol for c in self.option_chain.contracts}

    def family_hints(self) -> dict:
        """Per-strategy-family outcome hints for this window ({} when absent)."""
        return dict(self.family_outcome_hints)


def load_walk_forward_window(path: Path | str) -> WalkForwardWindow:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return WalkForwardWindow.from_dict(data)


def load_walk_forward_windows(directory: Path | str | None = None) -> list[WalkForwardWindow]:
    """Load all walk-forward fixture windows from a directory, sorted by sequence_id."""
    d = Path(directory) if directory else WALK_FORWARD_DIR
    windows: list[WalkForwardWindow] = []
    for jf in sorted(d.glob("window_*.json")):
        if jf.name.endswith("_analysis.json"):
            continue  # analysis-context fixture, not a window
        windows.append(load_walk_forward_window(jf))
    windows.sort(key=lambda w: w.sequence_id)
    return windows
