#!/usr/bin/env bash

set -euo pipefail

if [[ "$#" -ne 1 ]]; then
  echo "Usage: $0 <minimum-collected-tests>"
  exit 2
fi

minimum_collected_tests="$1"
if ! [[ "${minimum_collected_tests}" =~ ^[0-9]+$ ]]; then
  echo "Minimum collected test count must be a non-negative integer: ${minimum_collected_tests}"
  exit 2
fi

shard_count="${CI_SHARD_COUNT:-4}"
if ! [[ "${shard_count}" =~ ^[1-9][0-9]*$ ]]; then
  echo "CI_SHARD_COUNT must be a positive integer: ${shard_count}"
  exit 2
fi

repository_root="$(git rev-parse --show-toplevel)"
manifest_path=".github/ci/fast_subset.txt"
scratch_directory="$(mktemp -d)"
trap 'rm -rf -- "${scratch_directory}"' EXIT

plan_path="${scratch_directory}/ci_shard_plan.json"
all_nodeids_path="${scratch_directory}/all_nodeids.txt"
: > "${all_nodeids_path}"

python -m operator_tools.ci_shards plan \
  --repository-root "${repository_root}" \
  --manifest "${manifest_path}" \
  --shards "${shard_count}" \
  --output "${plan_path}"

for shard_number in $(seq 1 "${shard_count}"); do
  selected_path="${scratch_directory}/shard_${shard_number}_files.txt"
  collection_path="${scratch_directory}/shard_${shard_number}_collection.txt"
  nodeids_path="${scratch_directory}/shard_${shard_number}_nodeids.txt"
  collected_files_path="${scratch_directory}/shard_${shard_number}_collected_files.txt"

  python -m operator_tools.ci_shards select \
    --repository-root "${repository_root}" \
    --manifest "${manifest_path}" \
    --shards "${shard_count}" \
    --shard "${shard_number}" \
    --output "${selected_path}"

  mapfile -t selected_files < "${selected_path}"
  if [[ "${#selected_files[@]}" -eq 0 ]]; then
    echo "Deterministic CI plan assigned no files to shard ${shard_number}."
    exit 1
  fi

  if ! python -m pytest --collect-only -q -p no:cacheprovider \
    "${selected_files[@]}" > "${collection_path}" 2>&1; then
    echo "Pytest collection failed for shard ${shard_number}:"
    cat "${collection_path}"
    exit 1
  fi

  grep -E '^tests/[^:]+\.py::' "${collection_path}" > "${nodeids_path}" || true
  if [[ ! -s "${nodeids_path}" ]]; then
    echo "Shard ${shard_number} collected no pytest node IDs:"
    cat "${collection_path}"
    exit 1
  fi

  sed 's/::.*//' "${nodeids_path}" | sort -u > "${collected_files_path}"
  if ! diff -u <(sort -u "${selected_path}") "${collected_files_path}"; then
    echo "Shard ${shard_number} did not collect every assigned test file exactly."
    exit 1
  fi

  cat "${nodeids_path}" >> "${all_nodeids_path}"
  echo "Shard ${shard_number}/${shard_count}: ${#selected_files[@]} files, $(wc -l < "${nodeids_path}") tests."
done

duplicate_nodeids="$(sort "${all_nodeids_path}" | uniq -d)"
if [[ -n "${duplicate_nodeids}" ]]; then
  echo "Pytest node IDs were assigned to more than one CI shard:"
  echo "${duplicate_nodeids}"
  exit 1
fi

collected="$(wc -l < "${all_nodeids_path}")"
if [[ "${collected}" -lt "${minimum_collected_tests}" ]]; then
  echo "Collected ${collected} tests; required at least ${minimum_collected_tests}."
  exit 1
fi

plan_hash="$(python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["plan_sha256"])' "${plan_path}")"
file_count="$(python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["test_file_count"])' "${plan_path}")"
echo "Validated ${collected} unique operational tests across ${file_count} files and ${shard_count} deterministic shards."
echo "CI shard plan SHA-256: ${plan_hash}"
