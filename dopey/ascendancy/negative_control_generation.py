"""Deterministic transformations for controls that should destroy apparent edge."""

from __future__ import annotations

import math
import random


def circular_shift(values: tuple[float, ...], offset: int) -> tuple[float, ...]:
    if len(values) < 2 or any(not math.isfinite(value) for value in values):
        raise ValueError("circular-shift control requires at least two finite values")
    normalized_offset = offset % len(values)
    if normalized_offset == 0:
        raise ValueError("circular-shift control must materially shift the series")
    return values[-normalized_offset:] + values[:-normalized_offset]


def deterministic_permutation(values: tuple[float, ...], seed: int) -> tuple[float, ...]:
    if len(values) < 2 or any(not math.isfinite(value) for value in values):
        raise ValueError("permutation control requires at least two finite values")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("permutation seed must be an integer")
    indexes = list(range(len(values)))
    generator = random.Random(seed)
    generator.shuffle(indexes)
    if indexes == list(range(len(values))):
        indexes = indexes[1:] + indexes[:1]
    return tuple(values[index] for index in indexes)


def invert_directional_signal(values: tuple[float, ...]) -> tuple[float, ...]:
    if not values or any(not math.isfinite(value) for value in values):
        raise ValueError("inversion control requires finite values")
    return tuple(-value for value in values)
