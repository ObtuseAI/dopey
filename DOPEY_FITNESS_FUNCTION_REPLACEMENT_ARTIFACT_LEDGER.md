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
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_input.json` records=`1` sha256=`532981fa87ebc30faf0dfdc67ed1317116ce538f6bd80022dbb0582222f3bb75`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_metric_components.jsonl` records=`8` sha256=`2448254b878db7f5377afb5cf82f23590d6690b7f9f69ea406edd0d58434ca25`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_penalties.jsonl` records=`12` sha256=`908696279cf2ea4e137c08e8ae38d2db0b7ac4ef810f366bcd4d7896ce607104`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_scorecards.jsonl` records=`1` sha256=`2894980d9216b81c74f92d60ba986cb57c47bdc9bdf41d18880859cf0921c631`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_rank_records.jsonl` records=`1` sha256=`e7fd3632028407c48dedccca24b81f6d7f7bd26993f5b30ead04a5b47027f3ad`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_promotion_gate.json` records=`1` sha256=`59f25d0ebd7e90df387dda62f4011ffc064b49299cc1d5f594066f97dd4f3d6d`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_decision.json` records=`1` sha256=`413beaa23687fe106ec2209ed3644ae940d07da6bb79575092844afc65429024`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\proxy_fitness_quarantine_findings.jsonl` records=`1447` sha256=`d6d8c25db961dbec31dc6ce63214653d3354156299565b62c80d68734fd5ed2a`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_quality_flags.jsonl` records=`20` sha256=`7865c520c30993d5d8b10f159326a0688ca1ccfa0d4f29dae548c03343718784`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_replacement_summary.json` records=`1` sha256=`25bb0dd5dae20f808c198586c597a8baa3e17c97bf19a7847afa7212748d757d`
- `C:\Users\CH\dopey\artifacts\dopey\fitness\fitness_replacement_proof.jsonl` records=`1` sha256=`e24ae069221f1c913726af7d0b29c522bbb9d9f360eea0743b4cd8d94f5f8f5a`
- `C:\Users\CH\dopey\dopey_data\fixtures\fitness\fitness_metric_component_cases.json` records=`1` sha256=`93a4b78a03acbdfda56f87c53fbfadc04889ca4f78ad6cab799254f5e457c18b`
- `C:\Users\CH\dopey\dopey_data\fixtures\fitness\fitness_penalty_cases.json` records=`1` sha256=`1de2744424512eb02f153d89bd307323f96a548209131b4339d46ade856df15c`
- `C:\Users\CH\dopey\dopey_data\fixtures\fitness\fitness_promotion_gate_cases.json` records=`1` sha256=`ba59d31e6777ba02794c2b838070df3715b5498f3e77a6ad199daf9aa927bbc2`
- `C:\Users\CH\dopey\dopey_data\fixtures\fitness\proxy_fitness_quarantine_cases.json` records=`1` sha256=`d70e4140bb6dcfcecd58a2482376ef9047c82510d009d67422da8b8d07d383fa`
- `C:\Users\CH\dopey\DOPEY_FITNESS_FUNCTION_REPLACEMENT_REPORT.md` records=`53` sha256=`d1f3afeae65bb865afb9d08e0660662f0f4a0baefdac5bf12009b2f71d18e811`
- `C:\Users\CH\dopey\DOPEY_FITNESS_FUNCTION_REPLACEMENT_ARTIFACT_LEDGER.md` records=`59` sha256=`7b6e80f2bdffbee5ddbc303678c8d5001c4f2374fb3f91c3ed2d3d3ff63317c5`

## Record Counts
- score_component_count: `8`
- penalty_count: `12`
- rank_record_count: `1`
- blocked_active_proxy_promotion_count: `0`
- manual_review_proxy_reference_count: `387`

## Hashes
- fitness_replacement_summary.run_hash: `4bdfb2eccd050a171565dc4ad24b79d68e7516ec21872ef5022e4c7ed2dcfea2`

## Safety State
- paper_only: `true`
- live_blocked: `true`
- not_real_fitness_evidence: `true`
- promotion_allowed: `false`
- strategy_promoted: `false`
- no broker, credentials, scheduler, real sizing, or orders created
