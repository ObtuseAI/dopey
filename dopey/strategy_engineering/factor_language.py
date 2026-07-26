"""Small deterministic factor language with no future-data operators."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import TypedDict

from dopey.protocols.identity import canonical_hash


class FactorStep(TypedDict):
    step_id: str
    operator: str
    input_ids: tuple[str, ...]
    parameter: float


class FactorProgram(TypedDict):
    program_id: str
    program_version: str
    primitive_ids: tuple[str, ...]
    steps: tuple[FactorStep, ...]
    output_id: str
    future_data_operators_allowed: bool
    order_construction_allowed: bool


SUPPORTED_OPERATORS = frozenset({"MEAN", "DIFFERENCE", "PRODUCT", "CLIP", "THRESHOLD"})


def build_factor_program(primitive_ids: tuple[str, ...]) -> FactorProgram:
    if not primitive_ids or len(set(primitive_ids)) != len(primitive_ids):
        raise ValueError(f"factor program requires unique primitives: primitive_ids={primitive_ids}")
    steps: list[FactorStep] = []
    if len(primitive_ids) == 1:
        steps.append({"step_id": "factor_score", "operator": "MEAN", "input_ids": primitive_ids, "parameter": 0.0})
    else:
        steps.append({"step_id": "relative_component", "operator": "DIFFERENCE", "input_ids": primitive_ids[:2], "parameter": 0.0})
        steps.append({"step_id": "factor_score", "operator": "MEAN", "input_ids": ("relative_component", *primitive_ids[2:]), "parameter": 0.0})
    body = {
        "program_version": "dopey-factor-language-v1",
        "primitive_ids": primitive_ids,
        "steps": tuple(steps),
        "output_id": "factor_score",
        "future_data_operators_allowed": False,
        "order_construction_allowed": False,
    }
    return {"program_id": f"factor-program:{canonical_hash(body)[:24]}", **body}  # type: ignore[return-value]


def _validated_inputs(values: Mapping[str, Sequence[float]]) -> tuple[int, dict[str, tuple[float, ...]]]:
    if not values:
        raise ValueError("factor evaluation requires primitive value streams")
    normalized = {name: tuple(float(value) for value in stream) for name, stream in values.items()}
    lengths = {len(stream) for stream in normalized.values()}
    if len(lengths) != 1 or 0 in lengths:
        raise ValueError(f"factor primitive streams require one positive length: lengths={sorted(lengths)}")
    invalid = {name: tuple(value for value in stream if not math.isfinite(value)) for name, stream in normalized.items() if any(not math.isfinite(value) for value in stream)}
    if invalid:
        raise ValueError(f"factor primitive streams require finite values: invalid={invalid}")
    return next(iter(lengths)), normalized


def _evaluate_step(step: FactorStep, inputs: tuple[tuple[float, ...], ...], count: int) -> tuple[float, ...]:
    operator = step["operator"]
    if operator not in SUPPORTED_OPERATORS:
        raise ValueError(f"factor program contains an unsupported operator: operator={operator}")
    if operator == "MEAN":
        return tuple(sum(stream[index] for stream in inputs) / len(inputs) for index in range(count))
    if operator == "DIFFERENCE":
        if len(inputs) != 2:
            raise ValueError("DIFFERENCE requires exactly two inputs")
        return tuple(inputs[0][index] - inputs[1][index] for index in range(count))
    if operator == "PRODUCT":
        return tuple(math.prod(stream[index] for stream in inputs) for index in range(count))
    if operator == "CLIP":
        if len(inputs) != 1 or step["parameter"] <= 0.0:
            raise ValueError("CLIP requires one input and a positive symmetric bound")
        bound = step["parameter"]
        return tuple(max(-bound, min(bound, value)) for value in inputs[0])
    if operator == "THRESHOLD":
        if len(inputs) != 1:
            raise ValueError("THRESHOLD requires exactly one input")
        return tuple(1.0 if value >= step["parameter"] else 0.0 for value in inputs[0])
    raise ValueError(f"factor program operator dispatch is incomplete: operator={operator}")


def evaluate_factor_program(
    program: FactorProgram,
    primitive_values: Mapping[str, Sequence[float]],
) -> tuple[float, ...]:
    if program["future_data_operators_allowed"] or program["order_construction_allowed"]:
        raise ValueError(f"factor program violates research-only authority: program_id={program['program_id']}")
    count, values = _validated_inputs(primitive_values)
    missing = sorted(set(program["primitive_ids"]) - set(values))
    if missing:
        raise ValueError(f"factor program is missing primitive streams: program_id={program['program_id']}, missing={missing}")
    workspace = dict(values)
    for step in program["steps"]:
        if step["step_id"] in workspace:
            raise ValueError(f"factor step identity collides with an input or prior step: step_id={step['step_id']}")
        unresolved = sorted(set(step["input_ids"]) - set(workspace))
        if unresolved:
            raise ValueError(f"factor step references unresolved or future inputs: step_id={step['step_id']}, unresolved={unresolved}")
        inputs = tuple(workspace[input_id] for input_id in step["input_ids"])
        workspace[step["step_id"]] = _evaluate_step(step, inputs, count)
    if program["output_id"] not in workspace:
        raise ValueError(f"factor program output is unresolved: output_id={program['output_id']}")
    return workspace[program["output_id"]]
