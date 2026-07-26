"""Shared pytest bootstrap: sys.path setup + live-tree isolation for every test.

Why this exists
---------------
Many tests exercise real pipeline runners (fixture lane AND honest lane).
Runner modules bind absolute output paths at import time as module-level Path
constants (``REPO_ROOT / "artifacts" / "dopey" / ...``), so an unisolated test
run OVERWRITES the live pipeline artifacts (observed: fixture-tier records
stomping artifacts/dopey/signals/directional_setup_signals.jsonl and zeroing
the honest backtest) and rewrites tracked repo-root DOPEY_*.md reports.

The isolation layer
-------------------
* A session-scoped autouse fixture creates ONE isolated mirror tree per suite
  run (the legacy suite is written against a shared artifact tree - module- and
  session-scoped fixtures run runners whose outputs later tests read - so the
  mirror is shared across tests, but never the real live tree), then rewrites
  every already-imported module-level Path constant that points at:
    - the live ``artifacts/`` tree            -> <tmp>/artifacts/<rel>
    - a repo-root or docs/reports ``*.md``
      report/ledger (and the REPORTS_DIR
      binding itself)                         -> <tmp>/root_reports/<name>
    - a registered dopey_data WRITE target    -> <tmp>/dopey_data/<rel>
* The canonical ``dopey_data/real`` lake is copied once into the session
  mirror and every binding into that subtree is redirected. Several legacy
  negative-state tests temporarily move staged inputs; a read-only convention
  is not strong enough to protect the live lake when shards run concurrently.
  Tests still exercise a byte-for-byte snapshot of the real spine, manifests,
  staged chains, and news, but destructive fixture setup can only touch the
  disposable mirror.
* Large generated areas outside ``dopey_data/real`` remain selectively
  mirrored through the registered write zones below.
* An import hook (sys.meta_path) sweeps modules the moment they are executed,
  because runners import lazily DURING a test (the resilient supervisor's
  stage functions import runner modules at call time). A function-scoped
  autouse fixture re-sweeps as belt and braces.
* Honest-lane semantics are untouched: redirection only moves WHERE files
  land. The supervisor's injected-stages guard (``stages is not STAGES``)
  still skips the live journal/lock exactly as before.

tests/test_no_live_artifact_bindings.py proves closure over the entire
package tree (pattern reference: doofus tests/test_no_live_db_bindings.py).
"""
from __future__ import annotations

import hashlib
import importlib.abc
import importlib.machinery
import json
import os
import shutil
import sys
import zipfile
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path, PurePosixPath
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

TESTS_DIR = Path(__file__).resolve().parent
LIVE_ARTIFACTS_ROOT = REPO_ROOT / "artifacts"
LIVE_DATA_ROOT = REPO_ROOT / "dopey_data"
ARTIFACT_SEED_ARCHIVE = TESTS_DIR / "fixtures" / "runtime_artifact_seed_v1.zip"
ARTIFACT_SEED_MANIFEST = TESTS_DIR / "fixtures" / "runtime_artifact_seed_v1_manifest.json"
PUBLIC_SOURCE_MANIFEST = REPO_ROOT / "PUBLIC_SOURCE_MANIFEST.json"
# Canonical generated-report location (dopey_core.repo_paths.REPORTS_DIR).
LIVE_REPORTS_DIR = REPO_ROOT / "docs" / "reports"

# Top-level import names swept by the isolation layer (plus every "dopey*"
# package and the test modules themselves).
ISOLATED_TOP_LEVEL_NAMES = frozenset({"operator_tools", "scripts", "_forked_blunder", "_forked_scripts"})

# dopey_data subtrees that pipeline runners WRITE into. Everything under
# dopey_data NOT matched here stays real + read-only.
DATA_WRITE_SUBTREES: tuple[Path, ...] = (
    LIVE_DATA_ROOT / "open_autonomy",
    LIVE_DATA_ROOT / "openbb_autonomy",
    LIVE_DATA_ROOT / "market_lake",  # wealth-engine lane's self-built lake (raw/normalized/cache/public/active)
    # Local-staging tests temporarily move these files to exercise the
    # missing-data path. Give every pytest process an exact private snapshot
    # so sharded runs cannot hide operator data from one another.
    LIVE_DATA_ROOT / "real" / "raw" / "daily_ohlcv",
    LIVE_DATA_ROOT / "real" / "raw" / "market_context",
    LIVE_DATA_ROOT / "real" / "raw" / "corporate_actions",
    LIVE_DATA_ROOT / "real" / "raw" / "daily_ohlcv_autonomous_open",
    LIVE_DATA_ROOT / "real" / "raw" / "market_context_autonomous_open",
    LIVE_DATA_ROOT / "real" / "raw" / "corporate_actions_autonomous_open",
    # self-materializing fixture families: their runners regenerate the whole
    # fixture set on every run (observed dirtying git), then read it back
    LIVE_DATA_ROOT / "fixtures" / "active_trading_policy",
    LIVE_DATA_ROOT / "fixtures" / "broker_readiness",
    LIVE_DATA_ROOT / "fixtures" / "operator_reviewed_ohlcv_stage",
    LIVE_DATA_ROOT / "fixtures" / "wealth_engine",
)

# Files under dopey_data/real/manifests that are runner WRITE targets. The
# canonical manifests (real_data_manifest.json, options_data_manifest.json,
# macro_context_manifest.json, history_dataset_manifest.json) are read-only
# inputs and stay real.
DATA_WRITE_FILENAMES = frozenset(
    {
        "real_data_manifest.draft.json",
        "real_data_manifest.candidate.json",
        "real_data_manifest.json",
        "autonomous_open_data_manifest.json",
    }
)

DATA_READ_SEEDS: tuple[Path, ...] = (
    Path("market_lake/manifests/market_lake_manifest.json"),
    Path("real/manifests/real_data_manifest.json"),
)

ROOT_REPORT_READ_SEEDS: tuple[Path, ...] = (
    Path("DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6_REPORT.md"),
    Path("DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6_ARTIFACT_LEDGER.md"),
    Path("DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V6_COMMANDS.md"),
    Path("DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7_REPORT.md"),
    Path("DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7_ARTIFACT_LEDGER.md"),
    Path("DOPEY_PUBLIC_SIGNAL_RESEARCH_BREAKTHROUGH_V7_COMMANDS.md"),
)

DATA_READ_MIRROR_SUBTREES: tuple[Path, ...] = (
    LIVE_DATA_ROOT / "real",
    LIVE_DATA_ROOT / "fixtures",
)

# Explicit (module, attr) write-target registry for constants that point into
# otherwise-read-only dopey_data zones. The operator fetch tools are staging
# WRITERS over the canonical raw dirs; no test may ever stomp staged data
# even if one accidentally invokes them.
DATA_WRITE_CONSTANTS = frozenset(
    {
        ("dopey_data_ingestion.ingestion_readiness_decision", "REAL_DATA_MANIFEST_PATH"),
        ("dopey_data_ingestion.local_staging_contract", "MANIFEST_DIR"),
        ("dopey_data_ingestion.local_staging_contract", "RAW_ROOT"),
        ("dopey_data_ingestion.local_staging_contract", "REAL_DATA_MANIFEST_PATH"),
        ("dopey_data_ingestion.local_staging_contract", "REAL_DATA_ROOT"),
        ("dopey_data_ingestion.local_staging_contract", "TEMPLATE_DIR"),
        ("dopey_data_ingestion.local_staging_contract", "VALIDATED_DIR"),
        ("dopey_data_ingestion.manual_ohlcv_manifest_draft", "MANIFEST_DIR"),
        ("dopey_data_ingestion.operator_reviewed_ohlcv_manifest_candidate", "MANIFEST_DIR"),
        ("dopey_data_ingestion.run_real_data_ingestion_plan", "FIXTURE_DIR"),
        ("dopey_data_ingestion.schema_contracts", "TEMPLATE_DIR"),
        # single-file fixture materializers inside otherwise read-only fixture dirs
        ("dopey_allocation.run_proof_weighted_allocator", "EXPECTED_ALLOCATION_PLAN_FIXTURE_PATH"),
        ("dopey_incident.run_incident_response_rehearsal", "EXPECTED_INCIDENT_SUMMARY_FIXTURE_PATH"),
        ("dopey_options.run_model_repricer", "MODEL_REPRICING_FIXTURE_CASES_PATH"),
        ("dopey_lifecycle.lifecycle_simulator", "LIFECYCLE_EXPECTED_PROOFS_FIXTURE_PATH"),
        ("dopey_lifecycle.lifecycle_simulator", "LIFECYCLE_EXPECTED_SUMMARY_FIXTURE_PATH"),
        ("dopey_portfolio.run_portfolio_replay", "EXPECTED_PORTFOLIO_REPLAY_SUMMARY_FIXTURE_PATH"),
        ("dopey_portfolio.run_portfolio_stress_ladder", "EXPECTED_STRESS_LADDER_SUMMARY_FIXTURE_PATH"),
        ("dopey_portfolio.run_portfolio_stress_ladder", "STRESS_LADDER_REPLAY_CASES_FIXTURE_PATH"),
        ("operator_tools.operator_fetch_daily_ohlcv", "REAL_DIR"),
        ("operator_tools.operator_fetch_daily_ohlcv", "HISTORY_DIR"),
        ("operator_tools.operator_fetch_daily_ohlcv", "REAL_MANIFEST_PATH"),
        ("operator_tools.operator_fetch_daily_ohlcv", "HISTORY_MANIFEST_PATH"),
        ("operator_tools.operator_fetch_macro_context", "MACRO_DIR"),
        ("operator_tools.operator_fetch_macro_context", "MACRO_MANIFEST_PATH"),
        ("operator_tools.operator_fetch_option_chains", "CHAIN_RAW_DIR"),
        ("operator_tools.operator_fetch_option_chains", "OPTIONS_MANIFEST_PATH"),
        ("operator_tools.operator_fetch_option_chains", "EARNINGS_OUT"),
    }
)

# (module, attr) pairs explicitly allowed to keep pointing into the live
# artifacts tree, READ-ONLY. Empty today; add entries ONLY for inputs a test
# must see from the real tree and can provably never write.
READONLY_LIVE_ARTIFACT_WHITELIST: frozenset[tuple[str, str]] = frozenset()

# Modules whose REPO_ROOT binding itself is redirected to the tmp root.
# These construct write paths by joining onto REPO_ROOT at RUNTIME
# (write_json(REPO_ROOT / "dopey_data" / "fixtures" / ...), _append_long_docs
# appending to REPO_ROOT / "DOPEY_CANON.md"), which per-constant rewriting
# cannot see. Audited: none of them reads real repo files through REPO_ROOT.
REPO_ROOT_REDIRECTED_BINDINGS = frozenset(
    {
        ("dopey_data_ingestion.ingestion_readiness_decision", "REPO_ROOT"),
        ("dopey_data_ingestion.local_ohlcv_file_inventory", "REPO_ROOT"),
        ("dopey_data_ingestion.local_staging_contract", "REPO_ROOT"),
        ("dopey_autonomy.autonomy_common", "REPO_ROOT"),
        ("dopey_autonomy.full_open_source_autonomous_orchestrator", "REPO_ROOT"),
        ("dopey_autonomy.run_finish_literally_everything_orchestrator", "REPO_ROOT"),
        ("dopey_autonomy.run_open_data_breakthrough_full_completion", "REPO_ROOT"),
        ("dopey_broker_readiness.read_only_detector_evidence_validator", "REPO_ROOT"),
        ("dopey_data_ingestion.local_ohlcv_file_inventory", "REPO_ROOT"),
        ("dopey_data_ingestion.operator_reviewed_ohlcv_staged_file_detector", "REPO_ROOT"),
        ("dopey_export.artifact_selector", "REPO_ROOT"),
        ("dopey_validation.safe_append_canon_validation_docs_v5", "REPO_ROOT"),
    }
)

# Modules the sweep must never touch (the isolation layer's own bindings).
_SWEEP_EXCLUDED_MODULES = frozenset({"conftest", __name__})

_STATE: dict[str, Path | None] = {"tmp_root": None}
_PATH_ORIGINALS: dict[tuple[str, str], Path] = {}
_DATA_READ_SEED_CONTENTS: dict[Path, bytes] = {}


def _is_under(path: Path, root: Path) -> bool:
    p = os.path.normcase(str(path))
    r = os.path.normcase(str(root))
    return p == r or p.startswith(r + os.sep)


def _relative_under(path: Path, root: Path) -> Path | None:
    if not _is_under(path, root):
        return None
    tail = str(path)[len(str(root)) :].lstrip("\\/")
    return Path(tail) if tail else Path(".")


def _is_data_write_target(path: Path, module_name: str, attr: str) -> bool:
    if (module_name, attr) in DATA_WRITE_CONSTANTS:
        return True
    if path.name in DATA_WRITE_FILENAMES:
        return True
    return any(_is_under(path, subtree) for subtree in DATA_WRITE_SUBTREES)


def redirect_target(original: Path, module_name: str, attr: str) -> Path | None:
    """Map a live-tree path to its isolated mirror; None = leave binding alone."""
    tmp_root = _STATE["tmp_root"]
    if tmp_root is None:
        return None
    if (module_name, attr) in READONLY_LIVE_ARTIFACT_WHITELIST:
        return None
    if (module_name, attr) in REPO_ROOT_REDIRECTED_BINDINGS and original == REPO_ROOT:
        return tmp_root
    rel = _relative_under(original, LIVE_ARTIFACTS_ROOT)
    if rel is not None:
        return tmp_root / "artifacts" / rel
    if (
        original.suffix.lower() == ".md"
        and original.parent in (REPO_ROOT, LIVE_REPORTS_DIR)
    ) or (original.parent == REPO_ROOT and original.name.endswith(".md.v5_backup")):
        return tmp_root / "root_reports" / original.name
    # Modules that join report filenames onto REPORTS_DIR at RUNTIME
    # (handoff packet builders, canon appenders) need the directory binding
    # itself redirected, mirroring the DATA_ROOT rule below.
    if attr.split("[", 1)[0] == "REPORTS_DIR" and original == LIVE_REPORTS_DIR:
        return tmp_root / "root_reports"
    rel = _relative_under(original, LIVE_DATA_ROOT)
    if rel is not None:
        if any(_is_under(original, subtree) for subtree in DATA_READ_MIRROR_SUBTREES):
            return tmp_root / "dopey_data" / rel
        if _is_data_write_target(original, module_name, attr):
            return tmp_root / "dopey_data" / rel
    # The wealth-engine lane joins market_lake/fixture paths onto DATA_ROOT at
    # RUNTIME (write_csv(DATA_ROOT / "market_lake" / ...)), which per-constant
    # rewriting cannot see. Every DATA_ROOT importer uses it exclusively for
    # that lane's self-built areas, so the root itself is redirected wherever
    # a module binds the name DATA_ROOT to the live dopey_data root.
    if attr.split("[", 1)[0] == "DATA_ROOT" and original == LIVE_DATA_ROOT:
        return tmp_root / "dopey_data"
    return None


def _sweep_container(value: object, module_name: str, attr: str) -> object | None:
    """Redirect Paths inside shallow containers. Returns a replacement object
    for immutable containers, None when mutated in place / nothing to do."""
    if isinstance(value, dict):
        for key in list(value.keys()):
            item = value[key]
            if isinstance(item, Path):
                target = redirect_target(item, module_name, f"{attr}[{key!r}]")
                if target is not None:
                    value[key] = target
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            if isinstance(item, Path):
                target = redirect_target(item, module_name, f"{attr}[{index}]")
                if target is not None:
                    value[index] = target
        return None
    if isinstance(value, (tuple, set, frozenset)):
        changed = False
        rebuilt = []
        for item in value:
            if isinstance(item, Path):
                target = redirect_target(item, module_name, attr)
                if target is not None:
                    rebuilt.append(target)
                    changed = True
                    continue
            rebuilt.append(item)
        if changed:
            return type(value)(rebuilt)
        return None
    return None


def _sweep_module(module: object) -> None:
    module_name = getattr(module, "__name__", "") or ""
    if module_name in _SWEEP_EXCLUDED_MODULES:
        return
    module_vars = getattr(module, "__dict__", None)
    if not isinstance(module_vars, dict):
        return
    for attr, value in list(module_vars.items()):
        if attr.startswith("__"):
            continue
        if isinstance(value, Path):
            target = redirect_target(value, module_name, attr)
            if target is not None:
                _PATH_ORIGINALS.setdefault((module_name, attr), value)
                module_vars[attr] = target
        elif isinstance(value, (dict, list, tuple, set, frozenset)):
            replacement = _sweep_container(value, module_name, attr)
            if replacement is not None:
                module_vars[attr] = replacement


def _is_isolated_module(name: str, module: object) -> bool:
    if name in _SWEEP_EXCLUDED_MODULES:
        return False
    top = name.partition(".")[0]
    if top.startswith("dopey") or top in ISOLATED_TOP_LEVEL_NAMES:
        return True
    module_file = getattr(module, "__file__", None)
    if module_file and _is_under(Path(module_file), TESTS_DIR):
        # test modules themselves: `from dopey_x import SOME_PATH` binds the
        # live Path object into the test module namespace at collection time.
        return True
    return False


def redirect_artifact_bindings() -> None:
    """Sweep every loaded test-visible module, rewriting live-tree bindings."""
    for name, module in list(sys.modules.items()):
        if module is None:
            continue
        if _is_isolated_module(name, module):
            _sweep_module(module)


def find_live_bindings() -> list[str]:
    """Diagnostics for the closure test: bindings the sweep should have moved
    but that still point into the live tree."""
    offenders: list[str] = []

    def _check(module_name: str, attr: str, value: object) -> None:
        if isinstance(value, Path) and redirect_target(value, module_name, attr) is not None:
            offenders.append(f"{module_name}.{attr} -> {value}")

    for name, module in list(sys.modules.items()):
        if module is None or not _is_isolated_module(name, module):
            continue
        module_vars = getattr(module, "__dict__", None)
        if not isinstance(module_vars, dict):
            continue
        for attr, value in list(module_vars.items()):
            if attr.startswith("__"):
                continue
            if isinstance(value, Path):
                _check(name, attr, value)
            elif isinstance(value, dict):
                for key, item in value.items():
                    _check(name, f"{attr}[{key!r}]", item)
            elif isinstance(value, (list, tuple, set, frozenset)):
                for item in value:
                    _check(name, f"{attr}[...]", item)
    return offenders


class _IsolationLoader(importlib.abc.Loader):
    """Wraps the real loader; sweeps the module right after execution so
    lazily-imported runners never expose a live write path to test code."""

    def __init__(self, wrapped: importlib.abc.Loader) -> None:
        self._wrapped = wrapped

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> ModuleType | None:
        return self._wrapped.create_module(spec)

    def exec_module(self, module: ModuleType) -> None:
        self._wrapped.exec_module(module)
        if _STATE["tmp_root"] is not None:
            _sweep_module(module)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


class _IsolationFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None,
    ) -> importlib.machinery.ModuleSpec | None:
        top = fullname.partition(".")[0]
        if not (top.startswith("dopey") or top in ISOLATED_TOP_LEVEL_NAMES):
            return None
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        if spec is None or spec.loader is None:
            return None  # namespace packages etc.: default machinery handles them
        spec.loader = _IsolationLoader(spec.loader)
        return spec


def _install_import_hook() -> None:
    if not any(isinstance(finder, _IsolationFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _IsolationFinder())


_install_import_hook()


@pytest.fixture(scope="session", autouse=True)
def isolated_live_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Create the per-run isolated mirror and redirect every loaded binding.

    Session-scoped so it runs BEFORE any module-/session-scoped test fixture
    (several of those invoke pipeline runners). Deliberately never undone:
    restoring live bindings at teardown would let post-suite hooks write live.
    """
    tmp_root = tmp_path_factory.mktemp("isolated_live_tree")
    for sub in ("artifacts", "root_reports", "dopey_data", "docs/reports"):
        (tmp_root / sub).mkdir(parents=True, exist_ok=True)
    _STATE["tmp_root"] = tmp_root
    _seed_declared_read_inputs(tmp_root)
    redirect_artifact_bindings()
    _neutralize_out_of_repo_writers()
    return tmp_root


def _neutralize_out_of_repo_writers() -> None:
    """Orchestrator full-runs copy session packets to the operator's desktop
    share (autonomy_common._shared_target_root probes C:/Users/*/Desktop and
    //FRANKENSTEIN). Tests must never write outside the repo: force the
    already-supported honest "no_shared_folder_available" branch."""
    from dopey_autonomy import autonomy_common
    from dopey_export import export_verifier

    def no_shared_target() -> None:
        return None

    def no_bundle_target(_bundle_id: str) -> None:
        return None

    autonomy_common._shared_target_root = no_shared_target
    export_verifier.first_available_shared_target = no_bundle_target


def _seed_manifest() -> dict[str, Any]:
    from operator_tools.build_test_artifact_seed import verify_test_artifact_seed

    value = verify_test_artifact_seed()
    if not isinstance(value, dict):
        raise TypeError(f"artifact seed manifest must be an object: path={ARTIFACT_SEED_MANIFEST}")
    if value.get("seed_version") != "dopey-runtime-artifact-seed-v1":
        raise ValueError(f"artifact seed manifest version is unsupported: path={ARTIFACT_SEED_MANIFEST}")
    if value.get("paper_only") is not True or value.get("live_blocked") is not True:
        raise ValueError(f"artifact seed manifest violates the paper-only boundary: path={ARTIFACT_SEED_MANIFEST}")
    files = value.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError(f"artifact seed manifest files map is empty: path={ARTIFACT_SEED_MANIFEST}")
    return value


def _extract_artifact_seed(tmp_root: Path) -> None:
    if not ARTIFACT_SEED_ARCHIVE.exists():
        raise FileNotFoundError(f"artifact seed archive is missing: path={ARTIFACT_SEED_ARCHIVE}")
    manifest = _seed_manifest()
    expected_archive_hash = str(manifest.get("archive_sha256", ""))
    actual_archive_hash = hashlib.sha256(ARTIFACT_SEED_ARCHIVE.read_bytes()).hexdigest()
    if actual_archive_hash != expected_archive_hash:
        raise ValueError(
            "artifact seed archive hash mismatch: "
            f"path={ARTIFACT_SEED_ARCHIVE}, expected={expected_archive_hash}, actual={actual_archive_hash}"
        )
    files_value = manifest["files"]
    if not isinstance(files_value, dict):
        raise TypeError(f"artifact seed files map must be an object: path={ARTIFACT_SEED_MANIFEST}")
    expected_names = set(str(name) for name in files_value)
    with zipfile.ZipFile(ARTIFACT_SEED_ARCHIVE, "r") as archive:
        archive_names = {info.filename for info in archive.infolist() if not info.is_dir()}
        if archive_names != expected_names:
            raise ValueError(
                "artifact seed archive contents do not match the manifest: "
                f"missing={sorted(expected_names - archive_names)}, extra={sorted(archive_names - expected_names)}"
            )
        for name in sorted(archive_names):
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise ValueError(f"artifact seed archive contains an unsafe path: name={name}")
            if relative.parts[0] != "artifacts":
                raise ValueError(f"artifact seed archive entry is outside artifacts/: name={name}")
            metadata = files_value[name]
            if not isinstance(metadata, dict):
                raise TypeError(f"artifact seed file metadata must be an object: name={name}")
            payload = archive.read(name)
            expected_hash = str(metadata.get("sha256", ""))
            actual_hash = hashlib.sha256(payload).hexdigest()
            if actual_hash != expected_hash:
                raise ValueError(
                    "artifact seed file hash mismatch: "
                    f"name={name}, expected={expected_hash}, actual={actual_hash}"
                )
            if len(payload) != int(metadata.get("bytes", -1)):
                raise ValueError(f"artifact seed file length mismatch: name={name}")
            target = tmp_root.joinpath(*relative.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)


def _public_clean_slate_enabled() -> bool:
    if not PUBLIC_SOURCE_MANIFEST.exists():
        return False
    value = json.loads(PUBLIC_SOURCE_MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"public source manifest must be an object: path={PUBLIC_SOURCE_MANIFEST}")
    expected = {
        "artifact_type": "dopey_public_source_manifest",
        "fresh_git_history": True,
        "real_market_data_included": False,
        "broker_credentials_included": False,
        "broker_account_history_included": False,
        "private_runtime_history_included": False,
    }
    mismatches = {
        key: {"expected": expected_value, "actual": value.get(key)}
        for key, expected_value in expected.items()
        if value.get(key) != expected_value
    }
    if mismatches:
        raise ValueError(
            "public source manifest violates the clean-slate test boundary: "
            f"path={PUBLIC_SOURCE_MANIFEST}, mismatches={mismatches}"
        )
    return True


def _seed_declared_read_inputs(tmp_root: Path) -> None:
    _extract_artifact_seed(tmp_root)
    public_clean_slate = _public_clean_slate_enabled()
    for source in DATA_READ_MIRROR_SUBTREES:
        if not source.exists() or not source.is_dir():
            raise FileNotFoundError(f"declared data mirror subtree is missing: source={source}")
        relative = source.relative_to(LIVE_DATA_ROOT)
        target = tmp_root / "dopey_data" / relative
        shutil.copytree(source, target, dirs_exist_ok=True)
    for relative in DATA_READ_SEEDS:
        source = LIVE_DATA_ROOT / relative
        if not source.exists():
            if public_clean_slate:
                continue
            raise FileNotFoundError(f"declared data read seed is missing: source={source}")
        payload = source.read_bytes()
        _DATA_READ_SEED_CONTENTS[relative] = payload
        target = tmp_root / "dopey_data" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    for relative in ROOT_REPORT_READ_SEEDS:
        source = LIVE_REPORTS_DIR / relative
        if not source.exists():
            raise FileNotFoundError(f"declared report read seed is missing: source={source}")
        target = tmp_root / "root_reports" / relative.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def _restore_data_read_inputs(tmp_root: Path) -> None:
    for relative, payload in _DATA_READ_SEED_CONTENTS.items():
        target = tmp_root / "dopey_data" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != payload:
            target.write_bytes(payload)


@pytest.fixture(autouse=True)
def _reassert_isolation(isolated_live_tree: Path) -> Iterator[None]:
    """Belt and braces: re-sweep before every test so anything imported by the
    previous test (or rebound by a stray monkeypatch.undo) is redirected."""
    _restore_data_read_inputs(isolated_live_tree)
    redirect_artifact_bindings()
    _neutralize_out_of_repo_writers()
    yield


def _require_isolated_checkpoints(isolated_root: Path, paths: Sequence[Path]) -> None:
    for path in paths:
        if not _is_under(path, isolated_root):
            raise ValueError(
                "public signal research checkpoint is outside the isolated tree: "
                f"path={path}, isolated_root={isolated_root}"
            )
        if not path.is_file():
            raise FileNotFoundError(f"public signal research checkpoint is missing: path={path}")


@pytest.fixture(scope="session")
def public_signal_research_v2_checkpoint(isolated_live_tree: Path) -> None:
    from dopey_autonomy.signal_research_common import LEADERBOARD_PATH, RESEARCH_ROOT

    _require_isolated_checkpoints(
        isolated_live_tree,
        (
            RESEARCH_ROOT / "public_signal_research_breakthrough_v1_summary.json",
            RESEARCH_ROOT / "research_breakthrough_gate_v1_summary.json",
            LEADERBOARD_PATH,
        ),
    )


@pytest.fixture(scope="session")
def public_signal_research_v3_checkpoint(isolated_live_tree: Path) -> None:
    from dopey_autonomy.signal_research_v3_common import (
        V2_CANDIDATE_SUMMARY_PATH,
        V2_GATE_SUMMARY_PATH,
        V2_MUTATION_QUEUE_SUMMARY_PATH,
        V2_SUMMARY_PATH,
        V2_TOURNAMENT_SUMMARY_PATH,
    )
    from dopey_autonomy.signal_research_v2_common import MUTATION_QUEUE_V2_PATH

    _require_isolated_checkpoints(
        isolated_live_tree,
        (
            V2_SUMMARY_PATH,
            V2_GATE_SUMMARY_PATH,
            V2_TOURNAMENT_SUMMARY_PATH,
            V2_CANDIDATE_SUMMARY_PATH,
            V2_MUTATION_QUEUE_SUMMARY_PATH,
            MUTATION_QUEUE_V2_PATH,
        ),
    )


@pytest.fixture(scope="session")
def public_signal_research_v4_checkpoint(isolated_live_tree: Path) -> None:
    from dopey_autonomy.signal_research_v3_common import (
        MUTATION_QUEUE_V3_PATH,
        RESEARCH_V3_ROOT,
    )

    _require_isolated_checkpoints(
        isolated_live_tree,
        (
            RESEARCH_V3_ROOT / "public_signal_research_breakthrough_v3_summary.json",
            RESEARCH_V3_ROOT / "research_breakthrough_gate_v3_summary.json",
            RESEARCH_V3_ROOT / "research_tournament_v3_summary.json",
            MUTATION_QUEUE_V3_PATH,
            RESEARCH_V3_ROOT / "research_mutation_queue_v3_summary.json",
            RESEARCH_V3_ROOT / "research_candidate_generator_v3_summary.json",
            RESEARCH_V3_ROOT / "research_signal_candidates_v3.jsonl",
            RESEARCH_V3_ROOT / "research_no_trade_filter_records_v3.jsonl",
            RESEARCH_V3_ROOT / "research_path_trades_v3.jsonl",
            RESEARCH_V3_ROOT / "research_tournament_holdout_scores_v3.jsonl",
            RESEARCH_V3_ROOT / "research_tournament_regime_scores_v3.jsonl",
            RESEARCH_V3_ROOT / "research_breakthrough_rejections_v3.jsonl",
            RESEARCH_V3_ROOT / "research_watchlist_candidates_v3.jsonl",
            RESEARCH_V3_ROOT / "stable_family_template_repair_v3_summary.json",
        ),
    )


@pytest.fixture(scope="session")
def public_signal_research_v5_checkpoint(isolated_live_tree: Path) -> None:
    from dopey_autonomy.public_champion_common import LIVE_GATE_ROOT, SCOREBOARD_ROOT
    from dopey_autonomy.signal_research_v5_common import (
        RESEARCH_V4_ROOT,
        V4_SUMMARY_PATH,
        V4_VALIDATION_SUMMARY_PATH,
    )

    _require_isolated_checkpoints(
        isolated_live_tree,
        (
            V4_SUMMARY_PATH,
            RESEARCH_V4_ROOT / "research_breakthrough_gate_v4_summary.json",
            RESEARCH_V4_ROOT / "research_tournament_v4_summary.json",
            RESEARCH_V4_ROOT / "research_mutation_queue_v4_summary.json",
            V4_VALIDATION_SUMMARY_PATH,
            SCOREBOARD_ROOT / "public_signal_research_scoreboard_v4.json",
            LIVE_GATE_ROOT / "public_signal_research_live_gate_status_v4.json",
        ),
    )


@pytest.fixture(scope="session")
def public_signal_research_v6_checkpoint(isolated_live_tree: Path) -> None:
    from dopey_autonomy.public_champion_common import SCOREBOARD_ROOT
    from dopey_autonomy.signal_research_v6_common import (
        V5_GATE_SUMMARY_PATH,
        V5_EXPENSIVE_LANE_SUMMARY_PATH,
        V5_LIVE_GATE_PATH,
        V5_MUTATION_QUEUE_PATH,
        V5_MUTATION_QUEUE_SUMMARY_PATH,
        V5_SUMMARY_PATH,
        V5_TIMEOUT_RECORDS_PATH,
        V5_VALIDATION_SUMMARY_PATH,
        V5_WATCHLIST_PATH,
    )

    _require_isolated_checkpoints(
        isolated_live_tree,
        (
            V5_SUMMARY_PATH,
            V5_GATE_SUMMARY_PATH,
            V5_EXPENSIVE_LANE_SUMMARY_PATH,
            V5_MUTATION_QUEUE_PATH,
            V5_MUTATION_QUEUE_SUMMARY_PATH,
            V5_WATCHLIST_PATH,
            V5_LIVE_GATE_PATH,
            V5_VALIDATION_SUMMARY_PATH,
            V5_TIMEOUT_RECORDS_PATH,
            SCOREBOARD_ROOT / "public_signal_research_scoreboard_v5.json",
        ),
    )


@pytest.fixture(scope="session")
def public_signal_research_v7_checkpoint(isolated_live_tree: Path) -> None:
    from dopey_autonomy.signal_research_v7_common import (
        V6_GATE_SUMMARY_PATH,
        V6_LIVE_GATE_PATH,
        V6_MUTATION_QUEUE_PATH,
        V6_MUTATION_QUEUE_SUMMARY_PATH,
        V6_SCOREBOARD_PATH,
        V6_SUMMARY_PATH,
        V6_TIMEOUT_RECORDS_PATH,
        V6_VALIDATION_SUMMARY_PATH,
        V6_WATCHLIST_PATH,
    )

    _require_isolated_checkpoints(
        isolated_live_tree,
        (
            V6_SUMMARY_PATH,
            V6_GATE_SUMMARY_PATH,
            V6_MUTATION_QUEUE_PATH,
            V6_MUTATION_QUEUE_SUMMARY_PATH,
            V6_WATCHLIST_PATH,
            V6_LIVE_GATE_PATH,
            V6_VALIDATION_SUMMARY_PATH,
            V6_TIMEOUT_RECORDS_PATH,
            V6_SCOREBOARD_PATH,
        ),
    )


@pytest.fixture()
def seed_live_artifact(isolated_live_tree: Path) -> Callable[[str], Path]:
    """Copy a REAL live-tree artifact into the isolated mirror.

    For tests whose subject is a consumer of prior pipeline outputs: seeds the
    read side without ever exposing the live tree to writes. Accepts a path
    relative to artifacts/ (e.g. "dopey/backtest/backtest_run_summary.json").
    """

    def _seed(relative: str) -> Path:
        source = LIVE_ARTIFACTS_ROOT / relative
        target = isolated_live_tree / "artifacts" / relative
        if not source.exists():
            raise FileNotFoundError(f"live artifact to seed does not exist: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
        return target

    return _seed
