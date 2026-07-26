"""Blunder universal code/artifact intelligence.

Blunder must reason over more than app code: JSON/YAML-ish config, schemas + instances, protocol-ish
command traces, encoded artifact filenames, proof ledgers, and source code. This module provides a real,
stdlib-only minimal JSON-Schema validator plus parsers/validators for several structured artifact kinds.
Everything here is deterministic and returns structured (ok, errors) results — no network, no eval.
"""
from __future__ import annotations

import ast
import json
import re
from typing import Any


# ----------------------------------------------------------------------------- minimal JSON-Schema validator
_TYPE_CHECKS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "null": lambda v: v is None,
}


def validate_against_schema(instance: Any, schema: dict, path: str = "$") -> list[str]:
    """Return a list of human-readable validation errors ([] == valid). A real subset of JSON Schema:
    type, enum, required, properties, additionalProperties(bool), items, minimum/maximum, minLength,
    minItems, pattern, const."""
    errors: list[str] = []
    if not isinstance(schema, dict):
        return [f"{path}: schema is not an object"]

    t = schema.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if not any(_TYPE_CHECKS.get(tt, lambda v: False)(instance) for tt in types):
            errors.append(f"{path}: expected type {t}, got {type(instance).__name__}")
            return errors  # type mismatch -> stop here (further checks would be noise)

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must equal const {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']}")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than minLength {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: does not match pattern {schema['pattern']}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: above maximum {schema['maximum']}")

    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property '{req}'")
        props = schema.get("properties", {})
        for k, subschema in props.items():
            if k in instance:
                errors += validate_against_schema(instance[k], subschema, f"{path}.{k}")
        addl = schema.get("additionalProperties", True)
        if addl is False:
            extra = [k for k in instance if k not in props]
            if extra:
                errors.append(f"{path}: additional properties not allowed: {extra}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than minItems {schema['minItems']}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                errors += validate_against_schema(item, item_schema, f"{path}[{i}]")
    return errors


def validate_schema_instance_pair(schema: dict, instance: Any) -> dict:
    errs = validate_against_schema(instance, schema)
    return {"kind": "schema_instance_pair", "ok": not errs, "errors": errs}


# ----------------------------------------------------------------------------- proof ledger (JSONL) intelligence
LEDGER_REQUIRED = {"run_id", "task_id", "final_status", "input_hash", "plan_hash",
                   "mock_trial_result", "execution_result", "validation_result"}
FINAL_STATES = {"PASS", "PASS_WITH_NOTES", "PARTIAL", "FAIL", "BLOCKED"}


def parse_proof_ledger(text: str) -> dict:
    """Parse an append-only JSONL proof ledger and check consistency."""
    entries, errors = [], []
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as e:
            errors.append(f"line {i+1}: invalid JSON ({e})")
    for j, e in enumerate(entries):
        missing = LEDGER_REQUIRED - set(e)
        if missing:
            errors.append(f"entry {j} ({e.get('run_id','?')}): missing {sorted(missing)}")
        fs = e.get("final_status")
        if fs is not None and fs not in FINAL_STATES:
            errors.append(f"entry {j} ({e.get('run_id','?')}): bad final_status {fs!r}")
    return {"kind": "proof_ledger", "ok": not errors, "entry_count": len(entries), "errors": errors}


# ----------------------------------------------------------------------------- command trace (protocol-ish) parser
_CMD_RE = re.compile(r"^\$\s*(.+)$")
_EXIT_RE = re.compile(r"^(?:exit|exit_code)\s*=\s*(-?\d+)\s*$", re.IGNORECASE)


def parse_command_trace(text: str) -> dict:
    """Parse a simple command trace ('$ cmd' lines followed by 'exit=N') into structured steps."""
    steps, errors, current = [], [], None
    for i, raw in enumerate(text.splitlines()):
        line = raw.strip()
        if not line:
            continue
        m = _CMD_RE.match(line)
        if m:
            if current is not None:
                steps.append(current)
            current = {"cmd": m.group(1).strip(), "exit": None, "line": i + 1}
            continue
        e = _EXIT_RE.match(line)
        if e and current is not None:
            current["exit"] = int(e.group(1))
    if current is not None:
        steps.append(current)
    for s in steps:
        if s["exit"] is None:
            errors.append(f"command '{s['cmd']}' (line {s['line']}) has no recorded exit code")
    failed = [s for s in steps if s["exit"] not in (None, 0)]
    return {"kind": "command_trace", "ok": not errors, "steps": steps,
            "failed_steps": failed, "errors": errors}


# ----------------------------------------------------------------------------- encoded artifact filename convention
# Obtuse convention seen in 30-proof-bundles: "<project>-<slug>-v<major>-<sha40>.bundle"
_NAME_RE = re.compile(
    r"^(?P<project>[a-z0-9]+)-(?P<slug>[a-z0-9-]+?)-v(?P<version>\d+)-(?P<sha>[0-9a-fA-F]{40})\.(?P<ext>[a-z0-9]+)$"
)


def decode_artifact_name(name: str) -> dict:
    """Decode an Obtuse encoded artifact filename into its parts (project/slug/version/sha/ext)."""
    m = _NAME_RE.match(name.strip())
    if not m:
        return {"kind": "encoded_filename", "ok": False, "errors": [f"'{name}' does not match the Obtuse artifact naming convention"]}
    d = m.groupdict()
    return {"kind": "encoded_filename", "ok": True, "parts": d, "errors": []}


# ----------------------------------------------------------------------------- source code intelligence
def analyze_python_source(text: str) -> dict:
    """Parse Python source (AST) -> syntax validity + a small structural summary."""
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return {"kind": "python_source", "ok": False, "errors": [f"SyntaxError: {e}"]}
    funcs = [n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    return {"kind": "python_source", "ok": True, "functions": len(funcs), "classes": len(classes),
            "function_names": funcs[:50], "class_names": classes[:50], "errors": []}


# ----------------------------------------------------------------------------- multi-artifact sweep (the demo)
def sweep(samples: dict) -> dict:
    """Run every available artifact analyzer over a samples dict and return a combined report.
    `samples` keys may include: proof_ledger_text, command_trace_text, encoded_names (list),
    schema_instance_pairs (list of {schema, instance, expect_valid}), python_text."""
    results: dict[str, Any] = {}
    if "proof_ledger_text" in samples:
        results["proof_ledger"] = parse_proof_ledger(samples["proof_ledger_text"])
    if "command_trace_text" in samples:
        results["command_trace"] = parse_command_trace(samples["command_trace_text"])
    if "encoded_names" in samples:
        results["encoded_filenames"] = [decode_artifact_name(n) for n in samples["encoded_names"]]
    if "schema_instance_pairs" in samples:
        pairs = []
        for p in samples["schema_instance_pairs"]:
            r = validate_schema_instance_pair(p["schema"], p["instance"])
            r["expect_valid"] = p.get("expect_valid", True)
            r["classification_correct"] = (r["ok"] == r["expect_valid"])
            pairs.append(r)
        results["schema_instance_pairs"] = pairs
    if "python_text" in samples:
        results["python_source"] = analyze_python_source(samples["python_text"])

    # overall ok: every analyzer ok, and every schema/instance classification correct.
    ok = True
    for k, v in results.items():
        if isinstance(v, dict) and v.get("ok") is False:
            ok = False
        if isinstance(v, list):
            for item in v:
                if item.get("kind") == "schema_instance_pair":
                    if not item.get("classification_correct", False):
                        ok = False
                elif item.get("ok") is False:
                    ok = False
    results["overall_ok"] = ok
    return results
