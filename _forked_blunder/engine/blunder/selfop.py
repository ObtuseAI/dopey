"""Blunder self-operation PREP (bounded).

Blunder may inspect its own engine, find weak modules, and PROPOSE small safe improvements — but it may not
deploy, weaken validators, delete gates, bypass approval, or claim self-improvement without proof. This module
only inspects + recommends; it makes no changes.
"""
from __future__ import annotations

from pathlib import Path

from .artifacts import analyze_python_source


def inspect_engine(engine_root: Path) -> dict:
    """Read-only inspection of Blunder's own python modules."""
    engine_root = Path(engine_root)
    modules = []
    for py in sorted(engine_root.rglob("*.py")):
        text = py.read_text(encoding="utf-8", errors="replace")
        a = analyze_python_source(text)
        modules.append({
            "path": str(py.relative_to(engine_root)).replace("\\", "/"),
            "loc": len(text.splitlines()),
            "syntax_ok": a["ok"],
            "functions": a.get("functions", 0),
            "classes": a.get("classes", 0),
            "has_tests": "test" in py.name.lower(),
            "todo_markers": text.upper().count("TODO") + text.upper().count("FIXME"),
        })
    return {"module_count": len(modules), "modules": modules}


def weak_module_scan(inspection: dict) -> list[dict]:
    """Heuristic weak-module signals (NOT a value judgment — just candidates for hardening)."""
    weak = []
    for m in inspection["modules"]:
        signals = []
        if not m["syntax_ok"]:
            signals.append("syntax error")
        if m["todo_markers"] > 0:
            signals.append(f"{m['todo_markers']} TODO/FIXME markers")
        if m["loc"] > 320:
            signals.append(f"large module ({m['loc']} loc) — consider splitting")
        if m["functions"] == 0 and m["classes"] == 0 and m["loc"] > 5:
            signals.append("no functions/classes (possible dead/placeholder module)")
        if signals:
            weak.append({"path": m["path"], "signals": signals})
    return weak


def self_operation_readiness(engine_root: Path) -> dict:
    insp = inspect_engine(engine_root)
    weak = weak_module_scan(insp)
    return {
        "report": "self_operation_readiness_report",
        "engine_root": str(engine_root),
        "module_count": insp["module_count"],
        "all_modules_syntax_ok": all(m["syntax_ok"] for m in insp["modules"]),
        "weak_module_candidates": weak,
        "safe_next_self_improvement_candidates": [
            {"id": "selfop-1", "title": "Add a unit-test module that runs the fixture loop + asserts statuses",
             "risk": "low", "validator": "python -m unittest", "gate": False},
            {"id": "selfop-2", "title": "Expand the minimal schema validator (oneOf/anyOf, $ref)",
             "risk": "low", "validator": "schema_instance fixtures (positive+negative)", "gate": False},
            {"id": "selfop-3", "title": "Add a real failure-taxonomy classifier to the repair loop",
             "risk": "low", "validator": "replay of recorded validation failures", "gate": False},
            {"id": "selfop-4", "title": "Wire a model-routing ledger stub (record-only)",
             "risk": "medium", "validator": "ledger consistency check", "gate": False},
        ],
        "risk_boundaries": {
            "allowed_without_gate": [
                "inspect own code", "propose small safe improvements", "run mock trials",
                "run validators", "create proof packets", "non-destructive edits inside engine workdir",
            ],
            "requires_human_gate": [
                "autonomous production deployment", "weakening validators", "deleting safety gates",
                "bypassing approval", "changing benchmark results", "networked/remote actions",
            ],
        },
        "validator_requirements": [
            "every self-improvement must pass a validator or replay before promotion",
            "proof-ledger consistency must remain green",
            "no PASS auto-consumed; PASS_WITH_NOTES used when repairs/notes occurred",
        ],
        "note": "This pass only inspects + recommends. No self-modification was performed.",
    }
