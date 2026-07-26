"""Dopey broker interface: abstract broker contract (broker-agnostic).

DOPEY-native. Every concrete broker adapter implements this. No method here may place a live
order unless the LiveOrderGate has approved; the default is paper/research only.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from .execution_intent import ExecutionIntent


class BrokerInterface(ABC):
    @abstractmethod
    def get_capabilities(self) -> dict:
        ...

    @abstractmethod
    def get_account_snapshot(self) -> dict:
        ...

    @abstractmethod
    def get_option_chain(self, symbol: str) -> dict:
        ...

    @abstractmethod
    def preview_order(self, intent: ExecutionIntent) -> dict:
        ...

    @abstractmethod
    def place_order(self, intent: ExecutionIntent) -> dict:
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> dict:
        ...
