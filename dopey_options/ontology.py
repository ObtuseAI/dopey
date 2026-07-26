"""Dopey options ontology: underlying / contract / chain dataclasses.

DOPEY-native (not forked). Stdlib dataclasses only — no pydantic — matching the Blunder engine
convention. These objects are the structural backbone for options research. They carry no
execution authority and no network calls. Defined-risk structures are preferred.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Underlying:
    symbol: str
    asset_class: str = "equity"
    price: float = 0.0
    currency: str = "USD"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Underlying":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class OptionContract:
    symbol: str
    underlying_symbol: str
    option_type: str  # "call" | "put"
    strike: float
    expiry: str  # ISO date
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    volume: int = 0
    open_interest: int = 0
    iv: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    rho: float = 0.0
    defined_risk: bool = True

    def mid(self) -> float:
        return round((self.bid + self.ask) / 2.0, 6) if self.bid > 0 and self.ask > 0 else self.last

    def spread_pct(self) -> float:
        if self.bid <= 0:
            return 1.0
        return round((self.ask - self.bid) / self.bid, 6)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "OptionContract":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class OptionChain:
    underlying: Underlying
    contracts: list[OptionContract] = field(default_factory=list)
    as_of: str = ""

    def calls(self) -> list[OptionContract]:
        return [c for c in self.contracts if c.option_type == "call"]

    def puts(self) -> list[OptionContract]:
        return [c for c in self.contracts if c.option_type == "put"]

    def min_open_interest(self, floor: int) -> list[OptionContract]:
        return [c for c in self.contracts if c.open_interest >= floor]

    def to_dict(self) -> dict:
        return {
            "underlying": self.underlying.to_dict(),
            "contracts": [c.to_dict() for c in self.contracts],
            "as_of": self.as_of,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "OptionChain":
        return cls(
            underlying=Underlying.from_dict(d["underlying"]),
            contracts=[OptionContract.from_dict(c) for c in d.get("contracts", [])],
            as_of=d.get("as_of", ""),
        )
