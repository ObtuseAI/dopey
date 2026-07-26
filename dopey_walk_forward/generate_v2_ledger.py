"""Generate the DOPEY_REGIME_HOLDOUT_CORPUS_V2_LEDGER.md ledger from the corpus v2 registry."""
from __future__ import annotations

import json
from pathlib import Path

from dopey_core.repo_paths import REPORTS_DIR
from dopey_walk_forward.regime_holdout_corpus_v2 import V2_REGISTRY_PATH


def _load_v2_registry_records() -> list[dict]:
    target = Path(V2_REGISTRY_PATH)
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    records = _load_v2_registry_records()
    if not records:
        print("V2 registry not found. Run python -m dopey_walk_forward.run_regime_holdout_corpus_v2 first.")
        return 1
    last = records[-1]
    coverage_score = last.get("coverage_score", {}) or {}
    lines: list[str] = []
    lines.append("# DOPEY REGIME/HOLDOUT CORPUS V2 LEDGER")
    lines.append("")
    lines.append(f"- corpus_v2_version: `{last.get('corpus_v2_version', '')}`")
    lines.append(f"- corpus_id: `{last.get('corpus_id', '')}`")
    lines.append(f"- total_windows: `{last.get('total_windows', 0)}`")
    lines.append(f"- new_windows_added: `{last.get('new_windows_added', 0)}`")
    lines.append(f"- splits_built: `{last.get('splits_built', 0)}`")
    lines.append(f"- coverage_fraction: `{round(coverage_score.get('coverage_fraction', 0.0), 6)}`")
    lines.append(f"- deterministic_hash: `{last.get('corpus_deterministic_hash', '')}`")
    lines.append("")
    lines.append("## Category distribution")
    for cat, count in sorted((last.get("category_window_count") or {}).items()):
        lines.append(f"- `{cat}`: {count}")
    lines.append("")
    lines.append("## Windows (deterministic fixture hash, regime, category, sector, macro, IV, liquidity, challenge)")
    strategy_scores = {s.get("strategy_id"): s for s in (last.get("strategy_consistency_scores") or [])}
    top_strategy = last.get("top_consistent_strategy_v2", "")
    top_family = last.get("top_consistent_family_v2", "")
    lines.append("")
    lines.append("## Top consistent strategy / family (v2)")
    lines.append(f"- top_consistent_strategy_v2: `{top_strategy}`")
    lines.append(f"- top_consistent_family_v2: `{top_family}`")
    lines.append("")
    lines.append("## Per-window fixture metadata (deterministic)")
    for w in last.get("split_replay_results", []) or []:
        sid = w.get("strategy_id", "")
        if sid != top_strategy:
            continue
        lines.append(f"- `{sid}` split_id=`{w.get('split_id','')}` split_type=`{w.get('split_type','')}` "
                     f"holdout_passed={w.get('holdout_passed',False)}")
    lines.append("")
    lines.append("## Window-level summary (from corpus v2 build)")
    # Pull the per-window metadata from the corpus itself (not the runner's per-strategy replay).
    from dopey_walk_forward.holdout_window_builder import build_regime_holdout_corpus_v2
    corpus = build_regime_holdout_corpus_v2()
    for w in corpus.windows:
        fp = w.expected_family_pressure
        lines.append(
            f"- `{w.window_id}` | regime=`{w.regime_tag}` | category=`{w.category}` | "
            f"sector=`{w.sector_context.sector}` | macro=`{w.macro_context.event_label}` | "
            f"iv=`{w.iv_surface_context.transition_label}` | liq=`{w.liquidity_context.stress_label}` | "
            f"challenge=`{w.challenge_context.challenge_label if w.challenge_context else '-'}` | "
            f"hash=`{w.deterministic_fixture_hash()[:12]}` | pressure_dc={fp.get('directional_convexity', 0):+.2f} "
            f"pressure_ve={fp.get('volatility_expansion', 0):+.2f} pressure_vc={fp.get('volatility_compression', 0):+.2f} "
            f"pressure_sd={fp.get('short_duration_defined_risk', 0):+.2f}"
        )
    out_path = REPORTS_DIR / "DOPEY_REGIME_HOLDOUT_CORPUS_V2_LEDGER.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
