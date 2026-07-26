# DOPEY Export Manifest Schema

## Manifest fields

- `manifest_id`: deterministic manifest id for the bundle.
- `bundle_id`: deterministic bundle id derived from selected artifact metadata.
- `created_at_utc`: deterministic timestamp field for reproducibility.
- `profile`: export profile.
- `artifact_count`: number of exported artifact entries in the manifest.
- `required_artifacts_present`: required artifact count present in the bundle.
- `optional_artifacts_present`: optional artifact count present in the bundle.
- `total_size_bytes`: total exported artifact bytes, excluding the manifest file itself.
- `bundle_sha256`: deterministic hash over exported relative paths, sizes, counts, and file hashes.
- `artifacts`: list of `ExportArtifact` records.
- `safety_state`: export-time safety state.
- `reproducibility_hash`: canonical hash over the manifest excluding this field.

## Artifact fields

- `artifact_id`
- `artifact_type`
- `source_path`
- `relative_export_path`
- `size_bytes`
- `sha256`
- `record_count`
- `parse_status`
- `required`
- `safety_scan_status`
- `notes`

## Required artifact types

- validation/canon/risk/broker boundary reports
- reporting dashboard index and dashboard artifacts
- reporting proof and summary
- audit summary, audit registries, and audit proof
- meta-governor registry/decisions/proof
- ensemble registry/proof
- tournament/champion proof records
- walk-forward and consistency proof records
- regime holdout corpus v2 records
- macro/IV/fundamental registries and proof records
- failure/mutation/feedback registries and proof records
- paper pipeline proof ledger
- generated Blunder integrity status reference

## Hash expectations

- Every exported file has a SHA256.
- The manifest has a canonical `reproducibility_hash`.
- The copy proof has a canonical `reproducibility_hash`.
- The audit performs strict hash replay for `export_manifest` and `export_copy_proof`.
- Bundle verification compares file count, bytes, relative paths, and SHA256 hashes.

## Safety scan expectations

- `active_forbidden_live_decisions` must be `0`.
- `credential_findings` must be `0`.
- `env_file_findings` must be `0`.
- `verification_blocked` must be `false`.
- Documentation may list forbidden live terms only as blocked/forbidden safety language.

## Copy proof fields

- `copy_proof_id`
- `bundle_id`
- `source_dir`
- `target_dir`
- `files_expected`
- `files_copied`
- `files_verified`
- `bytes_expected`
- `bytes_verified`
- `hash_mismatches`
- `missing_files`
- `extra_files`
- `verification_status`
- `reproducibility_hash`

## Current strict-hash export artifacts

- `export_manifest`
- `export_copy_proof`
