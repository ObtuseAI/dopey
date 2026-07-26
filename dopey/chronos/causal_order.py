"""Causal-parent validation for event streams."""

from __future__ import annotations

from collections.abc import Sequence

from dopey.protocols.identity import CausalIdentity


def validate_causal_order(events: Sequence[CausalIdentity]) -> None:
    observed: set[str] = set()
    for event in events:
        if event.parent_event_id and event.parent_event_id not in observed:
            raise ValueError(
                "causal parent is absent or appears after its child: "
                f"event_id={event.event_id}, parent_event_id={event.parent_event_id}"
            )
        if event.event_id in observed:
            raise ValueError(f"duplicate causal event identity: event_id={event.event_id}")
        observed.add(event.event_id)
