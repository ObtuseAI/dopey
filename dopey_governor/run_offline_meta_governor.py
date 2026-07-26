"""CLI for the deterministic DOPEY offline meta-governor."""
from __future__ import annotations

import json

from .meta_governor import run_offline_meta_governor


def main() -> int:
    summary = run_offline_meta_governor()
    concise = {
        "meta_governor_status": summary["meta_governor_status"],
        "mode": summary["mode"],
        "live_trading_enabled": summary["live_trading_enabled"],
        "strategies_evaluated": summary["strategies_evaluated"],
        "families_evaluated": summary["families_evaluated"],
        "paper_champions": summary["paper_champions"],
        "offline_ensemble_members": summary["offline_ensemble_members"],
        "quarantined": summary["quarantined"],
        "starved": summary["starved"],
        "research_only": summary["research_only"],
        "rejected": summary["rejected"],
        "forbidden_live_decisions_emitted": summary["forbidden_live_decisions_emitted"],
        "live_blocked": summary["live_blocked"],
        "registry_path": summary["registry_path"],
        "decisions_path": summary["decisions_path"],
        "proof_record_path": summary["proof_record_path"],
        "summary_path": summary["summary_path"],
    }
    print(json.dumps(concise, indent=2, sort_keys=True))
    return 0 if summary["meta_governor_status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
