"""Non-mutating text encoding guard for DOPEY documentation."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from dopey_research_pipeline.quality_ledger import reproducibility_hash


TEXT_ENCODING_GUARD_VERSION = "dopey-text-encoding-guard-v1"
REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "dopey" / "validation"
ENCODING_REPORT_PATH = ARTIFACT_DIR / "text_encoding_guard_report.json"


@dataclass(frozen=True)
class EncodingDiagnostic:
    path: str
    valid_utf8: bool
    invalid_offsets: list[int]
    original_sha256: str
    bytes_scanned: int
    text_encoding_guard_version: str = TEXT_ENCODING_GUARD_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def detect_invalid_utf8(path: Path | str) -> EncodingDiagnostic:
    target = Path(path)
    data = target.read_bytes()
    offsets: list[int] = []
    decoder = "utf-8"
    index = 0
    while index < len(data):
        try:
            data[index:].decode(decoder)
            break
        except UnicodeDecodeError as exc:
            absolute = index + exc.start
            offsets.append(absolute)
            index = absolute + 1
    return EncodingDiagnostic(
        path=str(target),
        valid_utf8=not offsets,
        invalid_offsets=offsets,
        original_sha256=hashlib.sha256(data).hexdigest(),
        bytes_scanned=len(data),
    )


def write_encoding_report(
    path: Path | str,
    report_path: Path | str = ENCODING_REPORT_PATH,
    preview_path: Path | str | None = None,
) -> dict:
    diagnostic = detect_invalid_utf8(path)
    preview = ""
    if preview_path is not None:
        preview = str(create_sanitized_preview(path, preview_path))
    record = {
        "text_encoding_guard_version": TEXT_ENCODING_GUARD_VERSION,
        "diagnostic": diagnostic.to_dict(),
        "non_mutating": True,
        "sanitized_preview_path": preview,
        "ascii_safe_append_supported": True,
    }
    record["reproducibility_hash"] = reproducibility_hash(record)
    target = Path(report_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def create_sanitized_preview(path: Path | str, preview_path: Path | str) -> Path:
    source = Path(path)
    target = Path(preview_path)
    text = source.read_bytes().decode("utf-8", errors="replace")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def ascii_safe_append(path: Path | str, text: str) -> None:
    text.encode("ascii")
    with Path(path).open("ab") as handle:
        payload = text
        if not payload.startswith("\n"):
            payload = "\n" + payload
        handle.write(payload.encode("ascii"))


def original_file_hash(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    target = REPO_ROOT / "DOPEY_CANON.md"
    preview = ARTIFACT_DIR / "DOPEY_CANON.sanitized.preview.md"
    record = write_encoding_report(target, ENCODING_REPORT_PATH, preview)
    print(json.dumps({
        "valid_utf8": record["diagnostic"]["valid_utf8"],
        "invalid_offsets": record["diagnostic"]["invalid_offsets"][:12],
        "report_path": str(ENCODING_REPORT_PATH),
        "sanitized_preview_path": str(preview),
        "non_mutating": record["non_mutating"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
