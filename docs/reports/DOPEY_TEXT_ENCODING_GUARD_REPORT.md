# DOPEY Text Encoding Guard Report

Session date: 2026-07-03

## Purpose

`dopey_validation.text_encoding_guard` was added to handle `DOPEY_CANON.md`
safely without destructive rewrites.

## Diagnostic

Command:

```text
python -m dopey_validation.text_encoding_guard
```

Result:

- valid_utf8: `false`
- non_mutating: `true`
- bytes_scanned: `41002`
- original_sha256:
  `E2D6CC68B894274A0B8D7A7F81A9CC8A22B6682684E041D49220DCE31C86FB66`
- invalid byte offsets:
  `25481`, `26172`, `26282`, `30069`, `30210`, `30326`, `30454`, `32151`

Artifacts:

- report: `artifacts/dopey/validation/text_encoding_guard_report.json`
- sanitized preview:
  `artifacts/dopey/validation/DOPEY_CANON.sanitized.preview.md`

## Policy

The guard does not rewrite the original file. It can:

- detect invalid UTF-8 bytes;
- report byte offsets;
- write a non-mutating diagnostic report;
- create a sanitized preview copy;
- support ASCII-only append operations.

The original `DOPEY_CANON.md` should not be normalized or replaced without
explicit approval.
