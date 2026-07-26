# DOPEY BLUNDER IMPORT REPORT

## Where the Blunder copy was found

Two complementary canonical sources on `Z:` were inspected:

1. **`Z:\Obtuse\engine\blunder\`** — the Blunder Recursive Work Engine V1 core (`core.py`,
   `engine.py`, `selfop.py`, `artifacts.py`, `benchmark.py`, `__init__.py`) plus `run_blunder.py`,
   `schemas/`, `fixtures/`, and the doctrine `README.md`.
2. **`Z:\BFORK-20260630-020500\blunder\inflow\`** — the 24-module inflow mesh (OSS-mining /
   source-trust / quarantine / license-gate concepts).

All other candidates were rejected (superseded / megabundle handoffs / benchmark slice /
single-file handoff / Kilo session storage).

## What was copied / forked

### Engine core → `dopey_core/` (renamed, logic preserved)
- `core.py` → `dopey_core/_kernel.py` (WorkPacket, statuses, fail-closed safety model, hashing).
  `DOPEY_VERSION = "0.1.0"`; `BLUNDER_LINEAGE_VERSION = "1.0.0"` kept. Task-id prefix
  `blunder-` → `dopey-`.
- `engine.py` → split into:
  - `dopey_core/proof_ledger.py` (ProofEntry + ProofLedger).
  - `dopey_core/autonomy_loop.py` (make_plan, Task, run loop).
  - `dopey_core/promotion_gate.py` (evaluate_lessons).
  - `dopey_core/rollback_manager.py` (bounded repair loop + containment).
- `selfop.py` → `dopey_core/adaptive_threshold_kernel.py` (inspect/recommend-only).
- `artifacts.py` → `dopey_core/validator_mesh.py` (JSON-Schema validator, ledger/command-trace/
  encoded-filename/source-code intelligence, multi-artifact sweep).
- `benchmark.py` → `dopey_core/replay_engine.py` (benchmark PREP + replay fixture builder).
- `schemas/` + `fixtures/` → `dopey_core/_schemas/` + `dopey_core/_fixtures/` (copied verbatim).
- `dopey_core/mutation_engine.py` (new; follows Blunder self-improvement doctrine, recommend-only).
- `dopey_core/config.py` (new; minimal flat-YAML loader, stdlib only).

### Inflow mesh → `dopey_oss_miner/` (renamed, logic preserved)
- `models.py` → `dopey_oss_miner/_models.py` (SourceCandidate, DopeyInflowRecord, build_record,
  stable_id). `BlunderInflowRecord` → `DopeyInflowRecord`.
- `license_gate.py` → `dopey_oss_miner/license_scanner.py`.
- `source_trust_scorer.py` + `inflow_ranker.py` → `dopey_oss_miner/source_value_ranker.py`
  (merged; both scoring functions preserved).
- `source_registry.py` → `dopey_oss_miner/repo_discovery.py` (Blunder-specific Obtuse artifact
  paths replaced with a Dopey-native research-only local-workspace builder; no network scraping).
- `quarantine_gate.py` → `dopey_oss_miner/import_sandbox.py`.
- `content_hasher.py` → `dopey_oss_miner/_content_hasher.py`.
- `secret_sentinel.py` → `dopey_oss_miner/_secret_sentinel.py`.
- `proof_artifact_miner.py` → `dopey_oss_miner/benchmark_extractor.py`.
- `promotion_bridge.py` → `dopey_oss_miner/promotion_recommender.py`.

## What was preserved verbatim (provenance only, not run as DOPEY code)
- `_forked_blunder/engine/` — full verbatim copy of `Z:\Obtuse\engine` (the original Blunder
  engine tree). Not imported by DOPEY runtime; kept for provenance.
- `_forked_blunder_tests/` — verbatim copy of `Z:\BFORK-20260630-020500\tests` (import `blunder`,
  so they are NOT run as DOPEY tests).
- `_forked_scripts/` — verbatim copy of the `blunder*.ps1` autonomy scripts.

## What was intentionally NOT modified
- The original Blunder sources on `Z:\Obtuse\engine` and `Z:\BFORK-20260630-020500` were **never
  modified**. A SHA256 baseline of all 78 source files was captured before the fork and
  re-verified after: **0 mismatches** (`Z_BLUNDER_SOURCES_UNCHANGED_OK`).

## Uncertain areas
- The inflow mesh has 24 modules; only the 8 with direct DOPEY lineage (license/trust/rank/
  registry/quarantine/hasher/sentinel/promotion/proof-miner) were forked-and-renamed into
  `dopey_oss_miner`. The remaining inflow modules (e.g. `consumer`, `normalizer`,
  `inflow_scheduler`, `recursive_feedback_engine`, `synthetic_drill_generator`,
  `visual_evidence_ingestor`, `runtime_telemetry_miner`, `agent_trace_miner`,
  `capability_extractor`, `code_symbol_extractor`, `contradiction_detector`, `provenance_tracker`,
  `replay_fixture_builder`) were NOT forked into DOPEY in this pass; they remain available in the
  `_forked_blunder/inflow` provenance copy for future ports.
- The Blunder `run_blunder.py` runner writes into the Obtuse workspace structure
  (`30-proof-bundles/`, `reports/...`). It is preserved in provenance but NOT wired into DOPEY
  runtime in the first pass.
