# Blunder Recursive Work Engine — V1 (runnable)

First runnable implementation of the Obtuse **P0 build lane** (Blunder capability / autonomy loop / proof-ledger
integration). Stdlib-only Python; every file effect is sandboxed to a per-run workdir; risky/irreversible packets
BLOCK without an operator gate. Aligned with the Blunder Fusion Doctrine (mock-before-execute, validate-before-
promote, explicit blocked states, one human gate, no auto-PASS, no validator weakening).

## Loop
intake → plan → mock trial → execute → validate → repair (≤3) → proof ledger → learn → repeat

## Run
```
cd engine
python run_blunder.py
```
Runs one complete proof cycle on a safe fixture task, the universal-artifact sweep, benchmark prep (mock-only),
and self-operation readiness; appends a proof-ledger entry and writes reports into the Obtuse structure.

## Layout
- `blunder/core.py` — work packet, statuses, hashing, safety / human-gate classification, intake.
- `blunder/engine.py` — plan engine, Task contract, mock→execute→validate→repair loop, append-only ProofLedger, lesson promotion.
- `blunder/artifacts.py` — universal code/artifact intelligence + a real minimal JSON-Schema validator
  (proof-ledger JSONL, command trace, encoded filename convention, schema+instance, Python source).
- `blunder/benchmark.py` — benchmark-prep harness (packet schema, mock replay, readiness report; **never scores**).
- `blunder/selfop.py` — self-operation readiness (inspect own engine, weak-module scan, safe candidates; recommend-only).
- `schemas/` — work_packet, proof_ledger_entry, benchmark_task_packet schemas (used by the validator).
- `fixtures/` — the safe fixture task (input/golden/output schema) + universal-artifact samples.
- `run_blunder.py` — CLI that drives all of the above and emits proof artifacts.

## Outputs (under the Obtuse workspace)
- `30-proof-bundles/proof-ledger.jsonl` — append-only proof ledger (self-validating).
- `30-proof-bundles/<run_id>/` — run-report, sweep-report, ledger-consistency, workdir/output.json.
- `reports/surgat-learning-promotions/<run_id>.json` — promoted / rejected lessons.
- `reports/benchmark-readiness/<run_id>.json`, `reports/self-operation/<run_id>.json`.

## Safety
Gate-free: local inspection, safe fixtures, dry runs, mock trials, tests, schema validation, local proof
generation, non-destructive workdir edits. Gate-required (fail-closed): production deploy, external services,
network/benchmark submission, destructive file ops, credentials, system changes, validator weakening.
