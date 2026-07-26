"""Generate a deterministic, read-only desktop state fixture for visual QA."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping, Sequence

from dopey_dashboard.control_center_state import build_control_center_state
from dopey_symbol_lab.lab import build_symbol_lab_state


def _redact_value(value: object, replacements: Mapping[str, str]) -> object:
    if isinstance(value, str):
        redacted = value
        for source, replacement in replacements.items():
            redacted = redacted.replace(source, replacement)
            redacted = redacted.replace(source.replace("\\", "/"), replacement)
        return redacted
    if isinstance(value, list):
        return [_redact_value(item, replacements) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _redact_value(item, replacements)
            for key, item in value.items()
        }
    return value


def _visual_projection(state: Mapping[str, object]) -> dict[str, object]:
    projected = dict(state)
    option_extremes = state.get("option_extremes")
    if isinstance(option_extremes, dict):
        projected_extremes = dict(option_extremes)
        projected_extremes.pop("hypotheses", None)
        projected_extremes.pop("forward_candidates", None)
        projected_extremes.pop("evaluation_manifests", None)
        projected["option_extremes"] = projected_extremes
    return projected


def generate_visual_fixture(repository_root: Path, output_path: Path) -> dict[str, object]:
    """Write one source-backed state fixture with host paths redacted."""

    root = repository_root.resolve()
    state = _visual_projection(build_control_center_state(root))
    redacted = _redact_value(
        state,
        {
            str(root): "<DOPEY_REPOSITORY>",
            str(Path.home().resolve()): "<USER_HOME>",
        },
    )
    if not isinstance(redacted, dict):
        raise TypeError("visual fixture state must remain an object after redaction")
    fixture = dict(redacted)
    symbol_lab = _redact_value(
        build_symbol_lab_state(root, "SPY", "auto", None, 14, 0.0),
        {
            str(root): "<DOPEY_REPOSITORY>",
            str(Path.home().resolve()): "<USER_HOME>",
        },
    )
    if not isinstance(symbol_lab, dict):
        raise TypeError("visual symbol-lab fixture must remain an object after redaction")
    fixture["visual_qa_symbol_lab"] = symbol_lab
    fixture["visual_qa"] = {
        "fixture_mode": True,
        "read_only": True,
        "source_backed": True,
        "host_paths_redacted": True,
        "mutation_authority": "none",
        "omitted_nonvisual_payloads": [
            "option_extremes.hypotheses",
            "option_extremes.forward_candidates",
            "option_extremes.evaluation_manifests",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(fixture, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return fixture


def _arguments(arguments: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(arguments)


def main(arguments: Sequence[str]) -> int:
    parsed = _arguments(arguments)
    fixture = generate_visual_fixture(parsed.repo_root, parsed.output)
    print(json.dumps({
        "status": "pass",
        "output": str(parsed.output.resolve()),
        "schema_version": fixture.get("schema_version"),
        "read_only": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
