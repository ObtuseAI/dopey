# DOPEY Watchdog Recovery and Resume Report

## Watchdog / Restart Investigation
- classification: `bugcheck_watchdog_timeout`
- confidence: `medium`
- Kernel-Power 41 count: `2`
- BugCheck/watchdog count: `2`
- unexpected shutdown 6008 count: `2`
- WHEA event count: `29`
- display-driver timeout count: `0`
- no system settings were changed.

## Repo Recovery Summary
- resume classification: `complete_needs_verification`
- partial artifact audit status: `issues_found`
- partial artifact findings: `32`
- corrupt or suspect findings: `30`
- `.env` present: `false`
- real raw file count: `0`
- suspect prior artifacts were preserved; no blind deletion was performed.

## Target Bundle Result
- bundle: `DOPEY_OPERATOR_REVIEWED_OHLCV_STAGE_RERUN_V1`
- target bundle status: `complete_verified_with_inconclusive_expensive_smokes`
- staged-file status: `operator_files_missing`
- source-review status: `operator_review_packet_missing`
- manifest candidate status: `blocked_missing_staged_files`
- final manifest status: `final_manifest_missing`
- local validator status: `missing_local_ohlcv_files`
- history activation status: `blocked_missing_local_ohlcv`
- real signal validation status: `blocked_missing_valid_real_history`
- evidence boundary status: `written`

## Validation Results
- targeted tests: `pass` pass=`12` fail=`0` timeout=`0`
- smokes: `issues_found` pass=`19` fail=`0` timeout=`3`
- export verifier status: `inconclusive_timeout`
- full pytest status: `not_run_watchdog_safe_no_uncapped_full_pytest`

## Timeout Results
- `p y t h o n   j s o n / j s o n l   p a r s e   a u d i t   o v e r   r e q u e s t e d   a r t i f a c t   d i r s`: `inconclusive_timeout` after `30` seconds
- `python -m dopey_audit.run_offline_evidence_replay_audit`: `inconclusive_timeout` after `75` seconds
- `python -m dopey_export.run_artifact_compaction_export_verifier`: `inconclusive_timeout` after `60` seconds
- `python -m dopey_validation.full_suite_stabilizer`: `inconclusive_timeout` after `60` seconds

## Safety State
- Alpha Vantage excluded: `true`
- network fetch performed: `false`
- broker connection used: `false`
- credentials created: `false`
- `.env` exists: `false`
- strategy promotion allowed: `false`

## Known Gaps
- No operator-reviewed OHLCV files are staged.
- Operator source-review packet is missing.
- Final manifest is missing.
- Expensive audit/export/stabilizer lanes timed out under watchdog-safe caps and remain inconclusive.

## Next Target
- `DOPEY_OPERATOR_STAGE_REVIEWED_FREE_OHLCV_FILES`
