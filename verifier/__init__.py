"""Protected verification boundary for DOPEY Ascendancy."""

from .environment_freeze import load_environment, validate_environment, verify_environment_freeze
from .path_policy import assert_candidate_write_path_allowed
from .protected_manifest import (
    ASCENDANCY_PROTECTED_PATHS,
    build_ascendancy_protected_manifest,
    build_protected_manifest,
    verify_ascendancy_protected_manifest,
    verify_protected_manifest,
)

__all__ = [
    "assert_candidate_write_path_allowed",
    "ASCENDANCY_PROTECTED_PATHS",
    "build_ascendancy_protected_manifest",
    "build_protected_manifest",
    "load_environment",
    "validate_environment",
    "verify_environment_freeze",
    "verify_ascendancy_protected_manifest",
    "verify_protected_manifest",
]
