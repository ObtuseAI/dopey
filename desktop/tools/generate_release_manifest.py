"""Generate explicit integrity and reproducibility metadata for the desktop release."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(path: Path, base: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(f"release manifest input is missing: path={path}")
    return {
        "path": path.relative_to(base).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def _tracked_inputs(repository_root: Path) -> list[Path]:
    patterns = (
        "desktop/assets/**/*",
        "desktop/dist/**/*",
        "desktop/src/**/*",
        "desktop/tools/**/*",
        "desktop/visual-qa/**/*",
        "dopey_acceleration/**/*.py",
        "dopey_symbol_lab/**/*.py",
    )
    discovered = [
        path
        for pattern in patterns
        for path in repository_root.glob(pattern)
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix.casefold() != ".pyc"
    ]
    fixed = [
        repository_root / "desktop" / "package-lock.json",
        repository_root / "desktop" / "package.json",
        repository_root / "desktop" / "pyproject.toml",
        repository_root / "desktop" / "requirements-build.in",
        repository_root / "desktop" / "requirements-build.lock",
        repository_root / "desktop" / "build_desktop.ps1",
        repository_root / "desktop" / "DOPEYControlCenter.spec",
        repository_root / "desktop" / "index.html",
        repository_root / "desktop" / "install_desktop_launcher.ps1",
        repository_root / "desktop" / "launch_desktop.ps1",
        repository_root / "desktop" / "README.md",
        repository_root / "desktop" / "tsconfig.app.json",
        repository_root / "desktop" / "tsconfig.json",
        repository_root / "desktop" / "tsconfig.node.json",
        repository_root / "desktop" / "vite.config.ts",
        repository_root / "dopey_dashboard" / "desktop_app.py",
        repository_root / "dopey_dashboard" / "chart_state.py",
        repository_root / "dopey_dashboard" / "control_center_state.py",
        repository_root / "dopey_dashboard" / "scheduler_control.py",
        repository_root / "dopey_analysis" / "two_coach_engine.py",
        repository_root / "dopey_analysis" / "__init__.py",
        repository_root / "dopey_analysis" / "trade_loss_coach.py",
        repository_root / "dopey_chart_vision" / "grounded_structure_engine.py",
        repository_root / "dopey_chart_vision" / "__init__.py",
        repository_root / "dopey_research_pipeline" / "__init__.py",
        repository_root / "dopey_research_pipeline" / "artifact_io.py",
        repository_root / "dopey" / "protocols" / "__init__.py",
        repository_root / "dopey" / "protocols" / "identity.py",
        repository_root / "dopey" / "technical" / "batch_a.py",
        repository_root / "dopey" / "technical" / "batch_d.py",
        repository_root / "dopey" / "technical" / "candle_intelligence.py",
        repository_root / "dopey" / "technical" / "foundry.py",
        repository_root / "dopey" / "technical" / "structure_patterns.py",
        repository_root / "operator_tools" / "acceleration_cycle.cmd",
        repository_root / "operator_tools" / "daily_ritual.cmd",
        repository_root / "operator_tools" / "run_scheduled_hidden.vbs",
    ]
    return sorted({*discovered, *fixed}, key=lambda path: str(path).casefold())


def _load_source_smoke(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise TypeError(f"source smoke result must be a JSON object: path={path}")
    expected_methods = [
        "close_window",
        "get_chart",
        "get_chart_coach",
        "get_state",
        "get_symbol_lab",
        "minimize_window",
        "set_instrument_mode",
        "set_llm_provider",
        "set_openrouter_api_key",
        "set_options_execution",
        "set_research_core",
        "toggle_maximize_window",
    ]
    if (
        payload.get("status") != "pass"
        or payload.get("server_started") is not False
        or payload.get("live_execution_enabled") is not True
        or payload.get("paper_only") is not False
        or payload.get("live_blocked") is not False
        or payload.get("desktop_api_methods") != expected_methods
    ):
        raise ValueError(f"source smoke contract is invalid: path={path}, payload={payload}")
    return payload


def _read_build_contract(repository_root: Path) -> dict[str, object]:
    spec_path = repository_root / "desktop" / "DOPEYControlCenter.spec"
    spec_text = spec_path.read_text(encoding="utf-8")
    if "upx=False" not in spec_text:
        raise ValueError(f"desktop release spec must disable UPX: path={spec_path}")
    python_hash_seed = os.environ.get("PYTHONHASHSEED")
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if python_hash_seed != "0":
        raise ValueError(f"PYTHONHASHSEED must be 0, found {python_hash_seed!r}")
    if source_date_epoch != "1784342400":
        raise ValueError(
            "SOURCE_DATE_EPOCH must be 1784342400, "
            f"found {source_date_epoch!r}"
        )
    return {
        "upx_enabled": False,
        "python_hash_seed": python_hash_seed,
        "source_date_epoch": source_date_epoch,
    }


def build_manifest(
    repository_root: Path,
    executable: Path,
    node_version: str,
    npm_version: str,
    authenticode_status: str,
    source_smoke_path: Path,
    packaged_smoke_passed: bool,
) -> dict[str, object]:
    inputs = [_file_record(path, repository_root) for path in _tracked_inputs(repository_root)]
    source_smoke = _load_source_smoke(source_smoke_path)
    build_contract = _read_build_contract(repository_root)
    return {
        "artifact_type": "dopey_desktop_release_manifest",
        "schema_version": "dopey-desktop-release-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "release": {
            "filename": executable.name,
            "bytes": executable.stat().st_size,
            "sha256": _sha256(executable),
            "authenticode_status": authenticode_status,
            "deployment_authorization": False,
        },
        "toolchain": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "pywebview": importlib.metadata.version("pywebview"),
            "pyinstaller": importlib.metadata.version("pyinstaller"),
            "node": node_version.strip(),
            "npm": npm_version.strip(),
            **build_contract,
            "python_dependency_lock_sha256": _sha256(
                repository_root / "desktop" / "requirements-build.lock"
            ),
            "node_dependency_lock_sha256": _sha256(
                repository_root / "desktop" / "package-lock.json"
            ),
        },
        "inputs": inputs,
        "runtime_contract": {
            "source_smoke_sha256": _sha256(source_smoke_path),
            "source_smoke_status": source_smoke["status"],
            "packaged_smoke_passed": packaged_smoke_passed,
            "renderer": source_smoke["renderer"],
            "server_started": source_smoke["server_started"],
            "paper_only": source_smoke["paper_only"],
            "live_blocked": source_smoke["live_blocked"],
            "live_execution_enabled": source_smoke["live_execution_enabled"],
            "desktop_api_methods": source_smoke["desktop_api_methods"],
        },
    }


def _arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--executable", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sha256-sidecar", type=Path, required=True)
    parser.add_argument("--node-version", required=True)
    parser.add_argument("--npm-version", required=True)
    parser.add_argument("--authenticode-status", required=True)
    parser.add_argument("--source-smoke", type=Path, required=True)
    parser.add_argument("--packaged-smoke-passed", action="store_true")
    return parser.parse_args(arguments)


def main(arguments: list[str]) -> int:
    parsed = _arguments(arguments)
    repository_root = parsed.repo_root.resolve()
    executable = parsed.executable.resolve()
    output = parsed.output.resolve()
    sidecar = parsed.sha256_sidecar.resolve()
    manifest = build_manifest(
        repository_root,
        executable,
        parsed.node_version,
        parsed.npm_version,
        parsed.authenticode_status,
        parsed.source_smoke.resolve(),
        parsed.packaged_smoke_passed,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    release = manifest["release"]
    if not isinstance(release, dict) or not isinstance(release.get("sha256"), str):
        raise TypeError("release manifest did not produce a SHA-256 string")
    sidecar.write_text(
        f"{release['sha256']}  {executable.name}\n",
        encoding="ascii",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
