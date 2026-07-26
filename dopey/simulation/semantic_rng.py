"""Order-independent deterministic random primitives.

Adapted from ``ObtuseAI/universal-sports-engine`` at commit
``72853d2`` under the MIT License.

Copyright (c) 2026 ObtuseAI
"""

from __future__ import annotations

import hashlib
import json
import math


_PERSONALIZATION = b"DOPEY-RNG1"


def _digest(root_seed: int, labels: tuple[str | int, ...]) -> bytes:
    if isinstance(root_seed, bool) or not isinstance(root_seed, int):
        raise TypeError(
            "semantic random root seed must be an integer: "
            f"actual={type(root_seed).__name__}"
        )
    if root_seed < 0:
        raise ValueError(
            f"semantic random root seed must be non-negative: root_seed={root_seed}"
        )
    if not labels:
        raise ValueError("semantic random draws require at least one label")
    normalized_labels: list[dict[str, str | int]] = []
    for label in labels:
        if isinstance(label, bool) or not isinstance(label, (str, int)):
            raise TypeError(
                "semantic random labels must be strings or integers: "
                f"actual={type(label).__name__}"
            )
        normalized_labels.append(
            {
                "label_type": "integer" if isinstance(label, int) else "string",
                "value": label,
            }
        )
    encoded = json.dumps(
        {
            "root_seed": root_seed,
            "labels": normalized_labels,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.blake2b(encoded, digest_size=8, person=_PERSONALIZATION).digest()


def semantic_seed(root_seed: int, *labels: str | int) -> int:
    """Return an order-independent integer seed addressed by semantic labels."""

    return int.from_bytes(_digest(root_seed, labels), "big")


def unit(root_seed: int, *labels: str | int) -> float:
    """Return a deterministic U[0, 1) draw addressed by semantic labels."""

    return semantic_seed(root_seed, *labels) / 2**64


def choice(root_seed: int, weights: tuple[float, ...], *labels: str | int) -> int:
    """Select a weighted index without mutable global or shared random state."""

    if not weights or any(
        not math.isfinite(weight) or weight < 0.0 for weight in weights
    ):
        raise ValueError(
            f"weights must be a non-empty finite non-negative tuple: weights={weights!r}"
        )
    total = math.fsum(weights)
    if total <= 0.0:
        raise ValueError(f"at least one weight must be positive: weights={weights!r}")
    threshold = unit(root_seed, *labels) * total
    cumulative = 0.0
    for index, weight in enumerate(weights):
        cumulative += weight
        if threshold < cumulative:
            return index
    return len(weights) - 1


def normal(
    root_seed: int,
    mean: float,
    standard_deviation: float,
    *labels: str | int,
) -> float:
    """Return a deterministic normal draw through a labelled Box-Muller pair."""

    if not math.isfinite(mean):
        raise ValueError(f"normal mean must be finite: mean={mean}")
    if not math.isfinite(standard_deviation) or standard_deviation < 0.0:
        raise ValueError(
            "normal standard deviation must be finite and non-negative: "
            f"standard_deviation={standard_deviation}"
        )
    first = max(unit(root_seed, *labels, "u1"), 1e-15)
    second = unit(root_seed, *labels, "u2")
    standard_normal = math.sqrt(-2.0 * math.log(first)) * math.cos(
        2.0 * math.pi * second
    )
    return mean + standard_deviation * standard_normal
