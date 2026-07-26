# DOPEY Fitness Function Replacement Artifact Ledger

## Source Files
- `dopey_fitness/fitness_models.py`
- `dopey_fitness/truth_gated_fitness_engine.py`
- `dopey_fitness/promotion_gate.py`
- `dopey_fitness/proxy_fitness_quarantine.py`
- `dopey_fitness/run_fitness_function_replacement.py`
- `tests/test_fitness_function_replacement.py`
- `dopey_audit/artifact_loader.py`
- `dopey_audit/audit_runner.py`
- `dopey_audit/evidence_models.py`
- `dopey_reporting/data_loader.py`
- `dopey_reporting/reporting_bundle.py`
- `dopey_export/artifact_selector.py`
- `dopey_export/artifact_compactor.py`
- `dopey_export/export_manifest.py`
- `dopey_export/export_safety_scanner.py`
- `dopey_export_review/review_packet.py`
- `dopey_export_review/review_models.py`
- `dopey_validation/full_suite_stabilizer.py`
- `pyproject.toml`

## Fixture Files
- `C:\Users\CH\dopey\dopey_data\fixtures\fitness\fitness_metric_component_cases.json` records=`21` sha256=`93a4b78a03acbdfda56f87c53fbfadc04889ca4f78ad6cab799254f5e457c18b`
- `C:\Users\CH\dopey\dopey_data\fixtures\fitness\fitness_penalty_cases.json` records=`27` sha256=`1de2744424512eb02f153d89bd307323f96a548209131b4339d46ade856df15c`
- `C:\Users\CH\dopey\dopey_data\fixtures\fitness\fitness_promotion_gate_cases.json` records=`18` sha256=`ba59d31e6777ba02794c2b838070df3715b5498f3e77a6ad199daf9aa927bbc2`
- `C:\Users\CH\dopey\dopey_data\fixtures\fitness\proxy_fitness_quarantine_cases.json` records=`20` sha256=`d70e4140bb6dcfcecd58a2482376ef9047c82510d009d67422da8b8d07d383fa`

## Artifact Files
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_input.json` records=`1` sha256=`d3d86160bd4cb51dbeb5cd8e232ae3e918660e28d8c3dce3d2ba2fc2e8adafcb`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_metric_components.jsonl` records=`8` sha256=`8b7622fbd12b9c6ce666de3a60b935d42f475658e9911d3b8cd07f5fbcb9bbfb`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_penalties.jsonl` records=`12` sha256=`ab8dff6eaf37e6539256c97b1360a9f8fb1bce2a94c7cfa092d22fc33109e2ca`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_scorecards.jsonl` records=`1` sha256=`9bfa3e95a18360b4c62d0318c67b51584250490baf1a53123858e03b76985391`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_rank_records.jsonl` records=`1` sha256=`e7fd3632028407c48dedccca24b81f6d7f7bd26993f5b30ead04a5b47027f3ad`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_promotion_gate.json` records=`1` sha256=`6670c16a668a35a71cb819f8d8d8034dd1a086f699b71535f2b99af2e33f9133`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_decision.json` records=`1` sha256=`1ff2117bdf0907bcdb527e4367d723c089de93950aff3747a7fe823a244405cf`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\proxy_fitness_quarantine_findings.jsonl` records=`1287` sha256=`e1b3bf2e89db8cce7f12152899de17d8e8b26f26cf8c1728ff13f942660e876e`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_quality_flags.jsonl` records=`19` sha256=`88505170ab21e49d9b5fa711b3263ae11e7b30ef91600d766377f7fa7199147d`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_replacement_summary.json` records=`1` sha256=`9e7da1a1c623c63cbb0c982d4f39d33b86cf7652e46ce26a49908ac8503b7756`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_replacement_proof.jsonl` records=`1` sha256=`e24ae069221f1c913726af7d0b29c522bbb9d9f360eea0743b4cd8d94f5f8f5a`
- `C:\Users\CH\dopey\dopey_data\fixtures\fitness\fitness_metric_component_cases.json` records=`1` sha256=`93a4b78a03acbdfda56f87c53fbfadc04889ca4f78ad6cab799254f5e457c18b`
- `C:\Users\CH\dopey\dopey_data\fixtures\fitness\fitness_penalty_cases.json` records=`1` sha256=`1de2744424512eb02f153d89bd307323f96a548209131b4339d46ade856df15c`
- `C:\Users\CH\dopey\dopey_data\fixtures\fitness\fitness_promotion_gate_cases.json` records=`1` sha256=`ba59d31e6777ba02794c2b838070df3715b5498f3e77a6ad199daf9aa927bbc2`
- `C:\Users\CH\dopey\dopey_data\fixtures\fitness\proxy_fitness_quarantine_cases.json` records=`1` sha256=`d70e4140bb6dcfcecd58a2482376ef9047c82510d009d67422da8b8d07d383fa`
- `C:\Users\CH\dopey\docs\reports\DOPEY_FITNESS_FUNCTION_REPLACEMENT_REPORT.md` records=`53` sha256=`46d6a70eb29c764fc34982b75cde16be7cfe67ac983ad276efeb712d1cdc05f0`
- `C:\Users\CH\dopey\docs\reports\DOPEY_FITNESS_FUNCTION_REPLACEMENT_ARTIFACT_LEDGER.md` records=`59` sha256=`af9a1a0e7b77c32dd4ab486b48dbe03e75591d395a40592ee1b7810345b3afd0`

## Record Counts
- score_component_count: `8`
- penalty_count: `12`
- rank_record_count: `1`
- blocked_active_proxy_promotion_count: `0`
- manual_review_proxy_reference_count: `397`

## Hashes
- fitness_replacement_summary.run_hash: `d75dbfdc7eeb80112c362c9b47b12c64a94d6ba96aa7096f919cceabce5ac9b4`

## Safety State
- paper_only: `true`
- live_blocked: `true`
- not_real_fitness_evidence: `true`
- promotion_allowed: `false`
- strategy_promoted: `false`
- no broker, credentials, scheduler, real sizing, or orders created
