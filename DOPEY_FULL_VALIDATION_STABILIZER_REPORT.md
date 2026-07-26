# DOPEY Full Validation Stabilizer Report

Session date: 2026-07-03

## Purpose

`dopey_validation.full_suite_stabilizer` was added to make full-suite validation
deterministic and diagnosable when plain `python -m pytest` is too slow or
inconclusive on Windows.

## Stabilizer Capabilities

- run collection only
- split tests by file
- run bounded per-file groups
- identify slow or inconclusive groups
- record timeouts as `inconclusive_timeout`
- detect Windows terminal flush `OSError: [Errno 22] Invalid argument`
- write a summary even when full suite does not complete
- never convert timeout into pass

Summary artifact:

- `artifacts/dopey/validation/full_suite_stabilizer_summary.json`

## Collection

Command:

```text
python -m pytest --collect-only -q
```

Result:

- status: `pass`
- tests collected: `654`
- duration: about `0.41s` in the direct run

## Bounded Stabilizer Run

Command:

```text
python -m dopey_validation.full_suite_stabilizer
```

Result:

- diagnostic_status: `full_inconclusive_or_failed`
- collection_status: `pass`
- full_suite_status: `inconclusive_timeout`
- timeout_recorded_as_pass: `false`
- windows_flush_oserror_seen: `false`
- summary_path: `artifacts/dopey/validation/full_suite_stabilizer_summary.json`

The bounded full-suite probe timed out after 30 seconds around 11 percent
progress. This is not a pass.

## Slow Group Identification

The first per-file group that exceeded the bounded diagnostic budget was:

```text
python -m pytest tests/test_artifact_compaction_export_verifier.py -q
```

The short stabilizer budget marked it `inconclusive_timeout` after about 6
seconds. A normal targeted run completed:

```text
python -m pytest tests/test_artifact_compaction_export_verifier.py -q
42 passed in 112.55s
```

This identifies the export verifier suite as slow rather than hanging.

## Full Pytest Status

Full `python -m pytest` remains inconclusive for this bundle. It should not be
reported as passing until either:

- the full suite completes under an agreed timeout, or
- the suite is split into validated deterministic groups with a documented
  rollup policy.

## Recommended Targeted Fixes

- Split full pytest by file or group in CI-style validation.
- Capture pytest output to files on Windows to avoid terminal flush errors
  masking final status.
- Keep active policy, audit, reporting, export, validation, and encoding tests
  as targeted gates.

## Test Shard Plan

The stabilizer now writes:

- `artifacts/dopey/validation/test_shard_plan.json`
- `DOPEY_TEST_SHARD_PLAN.md`

The shard plan includes per-file pytest commands, observed per-file durations
when available, a slow-test allowlist, and a recommended long-timeout command.
The slow allowlist includes:

- `tests/test_artifact_compaction_export_verifier.py`

The shard plan does not convert full-suite timeouts into passes.

## Account Ledger Bundle Validation Note

After the account-ledger bundle, `python -m pytest --collect-only -q`
collected `711` tests. The targeted account-ledger and active-policy ladder
passed, but the bounded full `python -m pytest -q` attempt timed out after
about `304` seconds. Full-suite status remains `inconclusive_timeout`, not
pass.
