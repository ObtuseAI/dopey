"""Private-local Windows service runner for DumbMoneyDopeyRobinhood.

The production entry point accepts only release-manifest arguments, loads one
SHA-256-pinned public config from ProgramData, reads the two secret values from
Windows Credential Manager, and starts in RECONCILIATION_ONLY.  Importing this
module performs no I/O, starts no thread, and makes no network request.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import hashlib
import json
import os
import re
import signal
import socket
import struct
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Final, Mapping, Protocol
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .control import (
    CONTROL_SCHEMA,
    OFFICIAL_ROBINHOOD_MCP,
    LiveBranchControl,
)
from .dumbmoney_authority import (
    DumbMoneyAuthorityError,
    _decode_public_key,
    _exact_fields,
    _sha256_text,
    _utc_timestamp,
    _verify_signed_wrapper,
    canonical_json_bytes,
)
from .dumbmoney_command_feed import (
    COMMAND_STATE_SCHEMA,
    CommandFeedHttpRequest,
    CommandFeedHttpResponse,
    CommandFeedTransport,
    DumbMoneyCommandDispatch,
    DumbMoneyCommandFeedClient,
    DumbMoneyCommandFeedError,
    command_feed_head,
)
from .dumbmoney_contract_feed import DumbMoneyContractResolverClient
from .dumbmoney_journal_anchor import (
    CoreJournalAnchorClient,
    JournalAnchorError,
)
from .ledger import (
    GENESIS_HASH,
    LEDGER_SCHEMA,
    LiveBranchLedgerError,
    ledger_path,
    paper_twin_path,
    read_ledger,
)
from .robinhood_gateway import (
    LOCAL_MODEL_BASE_URL,
    LOCAL_MODEL_PATTERN,
    LOCAL_MODEL_PROVIDER,
    RobinhoodAgenticGateway,
)
from .robinhood_mcp_direct import DeterministicRobinhoodMcpClient
from .service import run_live_branch_cycle

SERVICE_NAME: Final[str] = "DumbMoneyDopeyRobinhood"
CONFIG_SCHEMA: Final[str] = "dopey.dumbmoney-robinhood-runner-config.v1"
CORE_READINESS_SCHEMA: Final[str] = "dumbmoney.readiness-descriptor.v1"
HEALTH_SCHEMA: Final[str] = "dumbmoney.health.v1"
SIGNED_ENVELOPE_SCHEMA: Final[str] = "dumbmoney.signed-envelope.v1"
CORE_ENDPOINT_REF: Final[str] = "endpoint-ref:DumbMoneyCore"
CELL_TOKEN_TARGET_REF: Final[str] = "credential-target:DumbMoney/DopeyCellToken"
ROBINHOOD_PROFILE_TARGET_REF: Final[str] = (
    "credential-target:DumbMoney/RobinhoodProfile"
)
START_MODE: Final[str] = "RECONCILIATION_ONLY"
READINESS_REF: Final[str] = "readiness-ref:DumbMoneyDopeyRobinhood"
CELL_TOKEN_SECRET_REF: Final[str] = "secret-ref:dumbmoney-dopey-cell-token"
ROBINHOOD_PROFILE_SECRET_REF: Final[str] = "secret-ref:robinhood-agentic-mcp-profile"
CONFIG_RELATIVE_PATH: Final[Path] = (
    Path("DumbMoney") / "config" / "dopey-robinhood-runner.v1.json"
)
CORE_READINESS_RELATIVE_PATH: Final[Path] = (
    Path("DumbMoney") / "readiness" / "DumbMoneyCore.json"
)
READINESS_RELATIVE_PATH: Final[Path] = (
    Path("DumbMoney") / "readiness" / f"{SERVICE_NAME}.json"
)
DATA_ROOT_RELATIVE_PATH: Final[Path] = Path("DumbMoney") / "dopey-robinhood"
OLLAMA_EVIDENCE_RELATIVE_PATH: Final[Path] = (
    Path("evidence") / "ollama-runtime-evidence.v1.json"
)
MAXIMUM_CONFIG_BYTES: Final[int] = 262_144
MAXIMUM_READINESS_BYTES: Final[int] = 262_144
MAXIMUM_OLLAMA_MODELS_BYTES: Final[int] = 1_048_576
OLLAMA_MODELS_URL: Final[str] = f"{LOCAL_MODEL_BASE_URL.removesuffix('/v1')}/api/tags"
READINESS_KDF_DOMAIN: Final[bytes] = b"DumbMoneyDopeyRobinhood/readiness-ed25519/v1\0"
SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{64}$")
WINDOWS_SID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^S-1-5-(?:[0-9]+-){1,14}[0-9]+$"
)
CONFIG_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "service_name",
        "release_id",
        "core_endpoint_ref",
        "core_readiness_path",
        "core_cell_token_target",
        "robinhood_profile_target",
        "start_mode",
        "data_root",
        "readiness_ref",
        "readiness_path",
        "core_public_key_base64url",
        "operator_public_keys_base64url",
        "promoter_public_keys_base64url",
        "research_public_keys_base64url",
        "evaluator_public_keys_base64url",
        "expected_account_hash",
        "fund_lock_sha256",
        "service_manifest_sha256",
        "role_public_keys_sha256",
        "core_runner_config_sha256",
        "risk_policy_sha256",
        "readiness_signer_public_key_sha256",
        "codex_executable_path",
        "codex_executable_sha256",
        "codex_local_provider",
        "codex_local_model",
        "codex_local_model_digest",
        "ollama_executable_path",
        "ollama_executable_sha256",
        "ollama_process_identity_sid",
        "ollama_runtime_evidence_sha256",
        "poll_interval_seconds",
        "readiness_ttl_seconds",
    }
)
CORE_READINESS_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "schema",
        "service_name",
        "release_id",
        "instance_id",
        "process_id",
        "generation",
        "observed_at",
        "valid_until",
        "endpoint",
        "fund_lock_sha256",
        "service_manifest_sha256",
        "authority",
        "health",
        "capabilities",
    }
)


class DumbMoneyWindowsServiceError(RuntimeError):
    """A production service invariant failed closed."""


class CredentialProvider(Protocol):
    def read_bytes(self, target: str) -> bytes: ...


class WindowsCredentialManager:
    """Read one Windows generic credential without logging its value."""

    CRED_TYPE_GENERIC = 1

    def read_bytes(self, target: str) -> bytes:
        if not isinstance(target, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", target
        ):
            raise DumbMoneyWindowsServiceError("Windows credential target is invalid")
        if os.name != "nt":
            raise DumbMoneyWindowsServiceError("Windows Credential Manager is required")
        from ctypes import wintypes

        class FileTime(ctypes.Structure):
            _fields_ = [
                ("low_datetime", wintypes.DWORD),
                ("high_datetime", wintypes.DWORD),
            ]

        class CredentialAttribute(ctypes.Structure):
            _fields_ = [
                ("keyword", wintypes.LPWSTR),
                ("flags", wintypes.DWORD),
                ("value_size", wintypes.DWORD),
                ("value", ctypes.POINTER(ctypes.c_ubyte)),
            ]

        class Credential(ctypes.Structure):
            _fields_ = [
                ("flags", wintypes.DWORD),
                ("credential_type", wintypes.DWORD),
                ("target_name", wintypes.LPWSTR),
                ("comment", wintypes.LPWSTR),
                ("last_written", FileTime),
                ("credential_blob_size", wintypes.DWORD),
                ("credential_blob", ctypes.POINTER(ctypes.c_ubyte)),
                ("persist", wintypes.DWORD),
                ("attribute_count", wintypes.DWORD),
                ("attributes", ctypes.POINTER(CredentialAttribute)),
                ("target_alias", wintypes.LPWSTR),
                ("user_name", wintypes.LPWSTR),
            ]

        pointer = ctypes.POINTER(Credential)()
        advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        cred_read = advapi32.CredReadW
        cred_read.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(Credential)),
        ]
        cred_read.restype = wintypes.BOOL
        cred_free = advapi32.CredFree
        cred_free.argtypes = [ctypes.c_void_p]
        cred_free.restype = None
        if not cred_read(
            target,
            self.CRED_TYPE_GENERIC,
            0,
            ctypes.byref(pointer),
        ):
            error_code = ctypes.get_last_error()
            raise DumbMoneyWindowsServiceError(
                f"required Windows credential is unavailable; winerror={error_code}"
            )
        try:
            credential = pointer.contents
            size = int(credential.credential_blob_size)
            if not 1 <= size <= 16_384:
                raise DumbMoneyWindowsServiceError(
                    "Windows credential blob size is invalid"
                )
            return ctypes.string_at(credential.credential_blob, size)
        finally:
            cred_free(pointer)


@dataclass(frozen=True)
class DopeyRunnerConfig:
    release_id: str
    core_readiness_path: Path
    data_root: Path
    readiness_path: Path
    core_public_key: bytes
    operator_public_keys: Mapping[str, bytes]
    promoter_public_keys: Mapping[str, bytes]
    research_public_keys: Mapping[str, bytes]
    evaluator_public_keys: Mapping[str, bytes]
    expected_account_hash: str
    fund_lock_sha256: str
    service_manifest_sha256: str
    role_public_keys_sha256: str
    core_runner_config_sha256: str
    risk_policy_sha256: str
    readiness_signer_public_key_sha256: str
    codex_executable_path: Path
    codex_executable_sha256: str
    codex_local_model: str
    codex_local_model_digest: str
    ollama_executable_path: Path
    ollama_executable_sha256: str
    ollama_process_identity_sid: str
    ollama_runtime_evidence_sha256: str
    poll_interval_seconds: int
    readiness_ttl_seconds: int
    config_sha256: str


@dataclass(frozen=True)
class CoreEndpoint:
    base_url: str
    instance_id: str
    observed_at: str
    valid_until: str


@dataclass
class RunnerState:
    mode: str = START_MODE
    health_status: str = "DEGRADED"
    reason: str = "STARTING"
    core_ready: bool = False
    reconciled_once: bool = False
    execution_enabled: bool = False
    last_cycle_status: str = "not_started"
    command_sequence: int = 0
    command_digest: str = "0" * 64
    rollback_anchor_current: bool = False


class LoopbackHttpTransport(CommandFeedTransport):
    """HTTP transport that never uses proxies, redirects, or non-loopback hosts."""

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.trust_env = False

    def __call__(
        self,
        request: CommandFeedHttpRequest,
    ) -> CommandFeedHttpResponse:
        parsed = urlsplit(request.url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise DumbMoneyWindowsServiceError(
                "Core transport attempted a non-loopback request"
            )
        response = self._session.request(
            request.method,
            request.url,
            headers=dict(request.headers),
            data=request.body,
            timeout=request.timeout_seconds,
            allow_redirects=False,
        )
        return CommandFeedHttpResponse(
            status=response.status_code,
            headers=dict(response.headers),
            body=bytes(response.content),
        )


def _sha256_file(path: Path, label: str) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise DumbMoneyWindowsServiceError(f"{label} cannot be read") from error
    return digest.hexdigest()


def _windows_loopback_listener_owner(
    host: str,
    port: int,
) -> tuple[int, Path, str]:
    """Resolve one exact IPv4 loopback listener to its PID and image path."""

    if os.name != "nt":
        raise DumbMoneyWindowsServiceError(
            "Windows TCP listener ownership verification is required"
        )
    if (
        host != "127.0.0.1"
        or isinstance(port, bool)
        or not isinstance(port, int)
        or not 1 <= port <= 65_535
    ):
        raise DumbMoneyWindowsServiceError("loopback listener endpoint is invalid")
    from ctypes import wintypes

    class TcpRowOwnerPid(ctypes.Structure):
        _fields_ = [
            ("state", wintypes.DWORD),
            ("local_address", wintypes.DWORD),
            ("local_port", wintypes.DWORD),
            ("remote_address", wintypes.DWORD),
            ("remote_port", wintypes.DWORD),
            ("owning_process_id", wintypes.DWORD),
        ]

    get_table = ctypes.WinDLL("Iphlpapi.dll", use_last_error=True).GetExtendedTcpTable
    get_table.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
        wintypes.ULONG,
        ctypes.c_int,
        wintypes.ULONG,
    ]
    get_table.restype = wintypes.DWORD
    size = wintypes.DWORD(0)
    error = get_table(None, ctypes.byref(size), False, socket.AF_INET, 3, 0)
    if error not in {0, 122} or size.value <= ctypes.sizeof(wintypes.DWORD):
        raise DumbMoneyWindowsServiceError(
            "Windows TCP listener inventory is unavailable"
        )
    buffer = ctypes.create_string_buffer(size.value)
    error = get_table(buffer, ctypes.byref(size), False, socket.AF_INET, 3, 0)
    if error != 0:
        raise DumbMoneyWindowsServiceError(
            "Windows TCP listener inventory cannot be read"
        )
    count = ctypes.cast(buffer, ctypes.POINTER(wintypes.DWORD)).contents.value
    rows_address = ctypes.addressof(buffer) + ctypes.sizeof(wintypes.DWORD)
    rows = ctypes.cast(rows_address, ctypes.POINTER(TcpRowOwnerPid))
    owners: set[int] = set()
    for index in range(count):
        row = rows[index]
        address = socket.inet_ntoa(struct.pack("<I", row.local_address))
        local_port = socket.ntohs(row.local_port & 0xFFFF)
        if row.state == 2 and address == host and local_port == port:
            owners.add(int(row.owning_process_id))
    if len(owners) != 1:
        raise DumbMoneyWindowsServiceError(
            "exact Ollama loopback listener owner is absent or ambiguous"
        )
    process_id = owners.pop()
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    query_image = kernel32.QueryFullProcessImageNameW
    query_image.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    query_image.restype = wintypes.BOOL
    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    open_process_token = advapi32.OpenProcessToken
    open_process_token.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    open_process_token.restype = wintypes.BOOL
    get_token_information = advapi32.GetTokenInformation
    get_token_information.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    get_token_information.restype = wintypes.BOOL
    convert_sid = advapi32.ConvertSidToStringSidW
    convert_sid.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    convert_sid.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    local_free = kernel32.LocalFree
    local_free.argtypes = [wintypes.HLOCAL]
    local_free.restype = wintypes.HLOCAL
    handle = open_process(0x1000, False, process_id)
    if not handle:
        raise DumbMoneyWindowsServiceError(
            "Ollama listener process cannot be inspected"
        )
    try:
        capacity = wintypes.DWORD(32_768)
        image_buffer = ctypes.create_unicode_buffer(capacity.value)
        if not query_image(handle, 0, image_buffer, ctypes.byref(capacity)):
            raise DumbMoneyWindowsServiceError(
                "Ollama listener process image cannot be resolved"
            )
        token = wintypes.HANDLE()
        if not open_process_token(handle, 0x0008, ctypes.byref(token)):
            raise DumbMoneyWindowsServiceError(
                "Ollama listener process identity cannot be inspected"
            )
        try:
            token_size = wintypes.DWORD(0)
            get_token_information(
                token,
                1,
                None,
                0,
                ctypes.byref(token_size),
            )
            if token_size.value <= 0:
                raise DumbMoneyWindowsServiceError(
                    "Ollama listener process identity is unavailable"
                )
            token_buffer = ctypes.create_string_buffer(token_size.value)
            if not get_token_information(
                token,
                1,
                token_buffer,
                token_size,
                ctypes.byref(token_size),
            ):
                raise DumbMoneyWindowsServiceError(
                    "Ollama listener process identity cannot be read"
                )
            sid_pointer = ctypes.cast(
                token_buffer,
                ctypes.POINTER(ctypes.c_void_p),
            ).contents.value
            sid_text = wintypes.LPWSTR()
            if not sid_pointer or not convert_sid(
                sid_pointer,
                ctypes.byref(sid_text),
            ):
                raise DumbMoneyWindowsServiceError(
                    "Ollama listener process SID cannot be resolved"
                )
            try:
                process_sid = str(sid_text.value)
            finally:
                local_free(sid_text)
        finally:
            close_handle(token)
        return process_id, Path(image_buffer.value).resolve(), process_sid
    finally:
        close_handle(handle)


@dataclass(frozen=True)
class PinnedOllamaModelVerifier:
    """Verify the exact local Ollama tag manifest before each Codex spawn."""

    model: str
    digest: str
    executable_path: Path
    executable_sha256: str
    process_identity_sid: str
    static_evidence_path: Path
    static_evidence_sha256: str
    transport: CommandFeedTransport
    listener_owner_resolver: Callable[[str, int], tuple[int, Path, str]] = (
        _windows_loopback_listener_owner
    )

    def __call__(self) -> None:
        if (
            _sha256_file(
                self.static_evidence_path,
                "Ollama static installation attestation",
            )
            != self.static_evidence_sha256
        ):
            raise DumbMoneyWindowsServiceError(
                "Ollama static installation attestation SHA-256 mismatch"
            )
        owner_before = self._verify_listener_owner()
        response = self.transport(
            CommandFeedHttpRequest(
                method="GET",
                url=OLLAMA_MODELS_URL,
                headers={
                    "Accept": "application/json",
                    "Cache-Control": "no-store",
                },
                timeout_seconds=5.0,
            )
        )
        if response.status != 200:
            raise DumbMoneyWindowsServiceError(
                "local Ollama model inventory is unavailable"
            )
        if not 1 <= len(response.body) <= MAXIMUM_OLLAMA_MODELS_BYTES:
            raise DumbMoneyWindowsServiceError(
                "local Ollama model inventory size is invalid"
            )
        payload = _strict_json(response.body, "local Ollama model inventory")
        models = payload.get("models")
        if not isinstance(models, list) or len(models) > 1_000:
            raise DumbMoneyWindowsServiceError(
                "local Ollama model inventory is invalid"
            )
        matches = [
            item
            for item in models
            if isinstance(item, dict)
            and item.get("name") == self.model
            and item.get("model") == self.model
        ]
        if len(matches) != 1:
            raise DumbMoneyWindowsServiceError(
                "pinned local Ollama model is absent or ambiguous"
            )
        if matches[0].get("digest") != self.digest:
            raise DumbMoneyWindowsServiceError(
                "pinned local Ollama model digest mismatch"
            )
        owner_after = self._verify_listener_owner()
        if owner_after != owner_before:
            raise DumbMoneyWindowsServiceError(
                "Ollama listener ownership changed during verification"
            )

    def _verify_listener_owner(self) -> tuple[int, Path, str]:
        process_id, process_path, process_sid = self.listener_owner_resolver(
            "127.0.0.1",
            11_434,
        )
        if (
            isinstance(process_id, bool)
            or not isinstance(process_id, int)
            or process_id <= 0
            or process_path.resolve() != self.executable_path.resolve()
            or process_sid != self.process_identity_sid
        ):
            raise DumbMoneyWindowsServiceError(
                "Ollama listener is not owned by the pinned identity and executable"
            )
        if _sha256_file(process_path, "Ollama listener executable") != (
            self.executable_sha256
        ):
            raise DumbMoneyWindowsServiceError(
                "Ollama listener executable SHA-256 mismatch"
            )
        return process_id, process_path.resolve(), process_sid


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise DumbMoneyWindowsServiceError(
                    f"{label} contains a duplicate JSON key"
                )
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise DumbMoneyWindowsServiceError(
            f"{label} contains a non-finite number: {value}"
        )

    try:
        payload = json.loads(
            raw,
            object_pairs_hook=reject_duplicate,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DumbMoneyWindowsServiceError(
            f"{label} is not valid UTF-8 JSON"
        ) from error
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) for key in payload
    ):
        raise DumbMoneyWindowsServiceError(f"{label} must be a JSON object")
    return payload


def _digest(value: Any, label: str) -> str:
    try:
        return _sha256_text(value, label)
    except DumbMoneyAuthorityError as error:
        raise DumbMoneyWindowsServiceError(str(error)) from error


def _windows_sid(value: Any, label: str) -> str:
    if not isinstance(value, str) or not WINDOWS_SID_PATTERN.fullmatch(value):
        raise DumbMoneyWindowsServiceError(f"{label} must be a canonical Windows SID")
    return value


def _exact_path(value: Any, expected: Path, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise DumbMoneyWindowsServiceError(f"{label} must be an absolute path")
    try:
        resolved = Path(value).resolve()
    except OSError as error:
        raise DumbMoneyWindowsServiceError(f"{label} cannot be resolved") from error
    if resolved != expected.resolve():
        raise DumbMoneyWindowsServiceError(
            f"{label} differs from the fixed ProgramData path"
        )
    return resolved


def _absolute_file_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise DumbMoneyWindowsServiceError(f"{label} must be an absolute path")
    path = Path(value)
    if not path.is_absolute():
        raise DumbMoneyWindowsServiceError(f"{label} must be absolute")
    try:
        return path.resolve()
    except OSError as error:
        raise DumbMoneyWindowsServiceError(f"{label} cannot be resolved") from error


def _decode_key_map(value: Any, label: str) -> dict[str, bytes]:
    if not isinstance(value, dict) or not 1 <= len(value) <= 16:
        raise DumbMoneyWindowsServiceError(f"{label} must contain 1 to 16 public keys")
    keys: dict[str, bytes] = {}
    for raw_key_id, raw_key in value.items():
        key_id = _digest(raw_key_id, f"{label} key ID")
        if not isinstance(raw_key, str):
            raise DumbMoneyWindowsServiceError(
                f"{label} public-key encoding must be a string"
            )
        try:
            key = _decode_public_key(raw_key.encode("ascii"))
        except (UnicodeEncodeError, DumbMoneyAuthorityError) as error:
            raise DumbMoneyWindowsServiceError(
                f"{label} public key is invalid"
            ) from error
        if hashlib.sha256(key).hexdigest() != key_id:
            raise DumbMoneyWindowsServiceError(
                f"{label} key ID does not bind its public key"
            )
        keys[key_id] = key
    return keys


def load_runner_config(
    path: Path,
    expected_sha256: str,
    program_data: Path,
) -> DopeyRunnerConfig:
    """Load only the fixed public config and verify its exact raw bytes."""

    expected_digest = _digest(expected_sha256, "config_sha256")
    fixed_path = (program_data / CONFIG_RELATIVE_PATH).resolve()
    if path.resolve() != fixed_path:
        raise DumbMoneyWindowsServiceError(
            "runner config path is not the fixed ProgramData path"
        )
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise DumbMoneyWindowsServiceError(
            "pinned public runner config is unavailable"
        ) from error
    if not 1 <= len(raw) <= MAXIMUM_CONFIG_BYTES:
        raise DumbMoneyWindowsServiceError("runner config size is invalid")
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise DumbMoneyWindowsServiceError(
            "runner config does not match --config-sha256"
        )
    payload = _strict_json(raw, "runner config")
    try:
        _exact_fields(payload, CONFIG_FIELDS, "Dopey runner config")
    except DumbMoneyAuthorityError as error:
        raise DumbMoneyWindowsServiceError(str(error)) from error
    exact_values = {
        "schema": CONFIG_SCHEMA,
        "service_name": SERVICE_NAME,
        "core_endpoint_ref": CORE_ENDPOINT_REF,
        "core_cell_token_target": CELL_TOKEN_TARGET_REF,
        "robinhood_profile_target": ROBINHOOD_PROFILE_TARGET_REF,
        "start_mode": START_MODE,
        "readiness_ref": READINESS_REF,
        "codex_local_provider": LOCAL_MODEL_PROVIDER,
    }
    for field, expected in exact_values.items():
        if payload.get(field) != expected:
            raise DumbMoneyWindowsServiceError(
                f"runner config {field} is not the sealed value"
            )
    release_id = payload.get("release_id")
    if not isinstance(release_id, str) or not release_id.strip():
        raise DumbMoneyWindowsServiceError("runner config release_id must be nonempty")
    core_key_value = payload.get("core_public_key_base64url")
    if not isinstance(core_key_value, str):
        raise DumbMoneyWindowsServiceError(
            "runner config Core public key must be a string"
        )
    try:
        core_public_key = _decode_public_key(core_key_value.encode("ascii"))
    except (UnicodeEncodeError, DumbMoneyAuthorityError) as error:
        raise DumbMoneyWindowsServiceError(
            "runner config Core public key is invalid"
        ) from error
    operator_keys = _decode_key_map(
        payload.get("operator_public_keys_base64url"),
        "operator",
    )
    promoter_keys = _decode_key_map(
        payload.get("promoter_public_keys_base64url"),
        "promoter",
    )
    research_keys = _decode_key_map(
        payload.get("research_public_keys_base64url"),
        "research",
    )
    evaluator_keys = _decode_key_map(
        payload.get("evaluator_public_keys_base64url"),
        "evaluator",
    )
    role_ids = (
        {hashlib.sha256(core_public_key).hexdigest()}
        | set(operator_keys)
        | set(promoter_keys)
        | set(research_keys)
        | set(evaluator_keys)
    )
    expected_role_count = (
        1
        + len(operator_keys)
        + len(promoter_keys)
        + len(research_keys)
        + len(evaluator_keys)
    )
    if len(role_ids) != expected_role_count:
        raise DumbMoneyWindowsServiceError(
            "Core/operator/promoter/research public-key roles overlap"
        )
    poll_interval = payload.get("poll_interval_seconds")
    if (
        isinstance(poll_interval, bool)
        or not isinstance(poll_interval, int)
        or not 5 <= poll_interval <= 300
    ):
        raise DumbMoneyWindowsServiceError(
            "poll_interval_seconds must be from 5 through 300"
        )
    readiness_ttl = payload.get("readiness_ttl_seconds")
    if (
        isinstance(readiness_ttl, bool)
        or not isinstance(readiness_ttl, int)
        or not 10 <= readiness_ttl <= 120
    ):
        raise DumbMoneyWindowsServiceError(
            "readiness_ttl_seconds must be from 10 through 120"
        )
    local_model = payload.get("codex_local_model")
    if (
        not isinstance(local_model, str)
        or not LOCAL_MODEL_PATTERN.fullmatch(local_model)
        or local_model.endswith((":latest", ":cloud"))
    ):
        raise DumbMoneyWindowsServiceError(
            "codex_local_model must be an explicit non-cloud Ollama tag"
        )
    return DopeyRunnerConfig(
        release_id=release_id,
        core_readiness_path=_exact_path(
            payload.get("core_readiness_path"),
            program_data / CORE_READINESS_RELATIVE_PATH,
            "core_readiness_path",
        ),
        data_root=_exact_path(
            payload.get("data_root"),
            program_data / DATA_ROOT_RELATIVE_PATH,
            "data_root",
        ),
        readiness_path=_exact_path(
            payload.get("readiness_path"),
            program_data / READINESS_RELATIVE_PATH,
            "readiness_path",
        ),
        core_public_key=core_public_key,
        operator_public_keys=operator_keys,
        promoter_public_keys=promoter_keys,
        research_public_keys=research_keys,
        evaluator_public_keys=evaluator_keys,
        expected_account_hash=_digest(
            payload.get("expected_account_hash"),
            "expected_account_hash",
        ),
        fund_lock_sha256=_digest(
            payload.get("fund_lock_sha256"),
            "fund_lock_sha256",
        ),
        service_manifest_sha256=_digest(
            payload.get("service_manifest_sha256"),
            "service_manifest_sha256",
        ),
        role_public_keys_sha256=_digest(
            payload.get("role_public_keys_sha256"),
            "role_public_keys_sha256",
        ),
        core_runner_config_sha256=_digest(
            payload.get("core_runner_config_sha256"),
            "core_runner_config_sha256",
        ),
        risk_policy_sha256=_digest(
            payload.get("risk_policy_sha256"),
            "risk_policy_sha256",
        ),
        readiness_signer_public_key_sha256=_digest(
            payload.get("readiness_signer_public_key_sha256"),
            "readiness_signer_public_key_sha256",
        ),
        codex_executable_path=_absolute_file_path(
            payload.get("codex_executable_path"),
            "codex_executable_path",
        ),
        codex_executable_sha256=_digest(
            payload.get("codex_executable_sha256"),
            "codex_executable_sha256",
        ),
        codex_local_model=local_model,
        codex_local_model_digest=_digest(
            payload.get("codex_local_model_digest"),
            "codex_local_model_digest",
        ),
        ollama_executable_path=_absolute_file_path(
            payload.get("ollama_executable_path"),
            "ollama_executable_path",
        ),
        ollama_executable_sha256=_digest(
            payload.get("ollama_executable_sha256"),
            "ollama_executable_sha256",
        ),
        ollama_process_identity_sid=_windows_sid(
            payload.get("ollama_process_identity_sid"),
            "ollama_process_identity_sid",
        ),
        ollama_runtime_evidence_sha256=_digest(
            payload.get("ollama_runtime_evidence_sha256"),
            "ollama_runtime_evidence_sha256",
        ),
        poll_interval_seconds=poll_interval,
        readiness_ttl_seconds=readiness_ttl,
        config_sha256=expected_digest,
    )


def _credential_target(reference: str, expected: str) -> str:
    if reference != expected or not reference.startswith("credential-target:"):
        raise DumbMoneyWindowsServiceError(
            "credential reference is not the sealed target"
        )
    return reference.removeprefix("credential-target:")


def _secret_text(raw: bytes, label: str) -> str:
    try:
        value = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DumbMoneyWindowsServiceError(
            f"{label} credential is not UTF-8"
        ) from error
    if (
        not 16 <= len(value) <= 16_384
        or value != value.strip()
        or any(character in value for character in "\r\n\0")
    ):
        raise DumbMoneyWindowsServiceError(f"{label} credential has an invalid shape")
    return value


def load_secrets(
    provider: CredentialProvider,
) -> tuple[str, str]:
    """Load exactly two Credential Manager targets with no fallback."""

    cell_token = _secret_text(
        provider.read_bytes(
            _credential_target(CELL_TOKEN_TARGET_REF, CELL_TOKEN_TARGET_REF)
        ),
        CELL_TOKEN_SECRET_REF,
    )
    robinhood_profile = _secret_text(
        provider.read_bytes(
            _credential_target(
                ROBINHOOD_PROFILE_TARGET_REF,
                ROBINHOOD_PROFILE_TARGET_REF,
            )
        ),
        ROBINHOOD_PROFILE_SECRET_REF,
    )
    return cell_token, robinhood_profile


def _readiness_signer(cell_token: str) -> Ed25519PrivateKey:
    seed = hashlib.sha256(READINESS_KDF_DOMAIN + cell_token.encode("utf-8")).digest()
    return Ed25519PrivateKey.from_private_bytes(seed)


def _core_endpoint_from_readiness(
    config: DopeyRunnerConfig,
    now_utc: datetime,
) -> CoreEndpoint:
    try:
        raw = config.core_readiness_path.read_bytes()
    except OSError as error:
        raise DumbMoneyWindowsServiceError(
            "signed Core readiness is unavailable"
        ) from error
    if not 1 <= len(raw) <= MAXIMUM_READINESS_BYTES:
        raise DumbMoneyWindowsServiceError("signed Core readiness size is invalid")
    envelope = _strict_json(raw, "signed Core readiness")
    try:
        wrapper = _verify_signed_wrapper(
            envelope,
            config.core_public_key,
            now_utc,
            enforce_current_window=True,
        )
    except DumbMoneyAuthorityError as error:
        raise DumbMoneyWindowsServiceError(
            f"signed Core readiness is invalid: {error}"
        ) from error
    if wrapper.body_schema != CORE_READINESS_SCHEMA:
        raise DumbMoneyWindowsServiceError("Core readiness body schema is unsupported")
    body = wrapper.body
    try:
        _exact_fields(body, CORE_READINESS_FIELDS, "Core readiness descriptor")
    except DumbMoneyAuthorityError as error:
        raise DumbMoneyWindowsServiceError(str(error)) from error
    if (
        body.get("schema") != CORE_READINESS_SCHEMA
        or body.get("service_name") != "DumbMoneyCore"
        or body.get("release_id") != config.release_id
    ):
        raise DumbMoneyWindowsServiceError(
            "Core readiness identity or release binding mismatch"
        )
    instance_id = str(body.get("instance_id", ""))
    try:
        if str(uuid.UUID(instance_id)) != instance_id:
            raise ValueError
    except (ValueError, AttributeError) as error:
        raise DumbMoneyWindowsServiceError(
            "Core readiness instance_id is invalid"
        ) from error
    process_id = body.get("process_id")
    generation = body.get("generation")
    if (
        isinstance(process_id, bool)
        or not isinstance(process_id, int)
        or process_id <= 0
        or isinstance(generation, bool)
        or not isinstance(generation, int)
        or generation < 0
    ):
        raise DumbMoneyWindowsServiceError(
            "Core readiness process or generation is invalid"
        )
    observed_at = str(body.get("observed_at", ""))
    valid_until = str(body.get("valid_until", ""))
    observed = _utc_timestamp(observed_at, "Core readiness observed_at")
    valid = _utc_timestamp(valid_until, "Core readiness valid_until")
    now = now_utc.astimezone(timezone.utc)
    if (
        not observed <= now < valid
        or valid - observed > timedelta(seconds=120)
        or wrapper.not_before_utc != observed
        or wrapper.expires_at_utc != valid
    ):
        raise DumbMoneyWindowsServiceError("Core readiness window is invalid or stale")
    for field, expected in (
        ("fund_lock_sha256", config.fund_lock_sha256),
        ("service_manifest_sha256", config.service_manifest_sha256),
    ):
        if body.get(field) != expected:
            raise DumbMoneyWindowsServiceError(f"Core readiness {field} pin mismatch")
    authority = body.get("authority")
    if not isinstance(authority, dict) or authority != {
        "broker": "NONE",
        "mode": "OFFLINE",
        "execution_enabled": False,
    }:
        raise DumbMoneyWindowsServiceError(
            "Core readiness claims invalid broker authority"
        )
    health = body.get("health")
    if not isinstance(health, dict):
        raise DumbMoneyWindowsServiceError("Core readiness health must be an object")
    health_pins = {
        "core_public_key_sha256": hashlib.sha256(config.core_public_key).hexdigest(),
        "role_public_keys_sha256": config.role_public_keys_sha256,
        "runner_config_sha256": config.core_runner_config_sha256,
        "risk_policy_sha256": config.risk_policy_sha256,
    }
    for field, expected in health_pins.items():
        if health.get(field) != expected:
            raise DumbMoneyWindowsServiceError(
                f"Core readiness health pin mismatch: {field}"
            )
    if health.get("status") not in {"READY", "DEGRADED"}:
        raise DumbMoneyWindowsServiceError("Core readiness health status is blocked")
    endpoint = body.get("endpoint")
    if not isinstance(endpoint, dict) or set(endpoint) != {
        "transport",
        "host",
        "port",
        "base_path",
    }:
        raise DumbMoneyWindowsServiceError("Core readiness endpoint is invalid")
    host = endpoint.get("host")
    port = endpoint.get("port")
    if (
        endpoint.get("transport") != "http"
        or host not in {"127.0.0.1", "::1"}
        or endpoint.get("base_path") != "/"
        or isinstance(port, bool)
        or not isinstance(port, int)
        or not 1024 <= port <= 65_535
    ):
        raise DumbMoneyWindowsServiceError(
            "Core readiness endpoint is not literal loopback HTTP"
        )
    base_url = f"http://[{host}]:{port}" if host == "::1" else f"http://{host}:{port}"
    return CoreEndpoint(
        base_url=base_url,
        instance_id=instance_id,
        observed_at=observed_at,
        valid_until=valid_until,
    )


def _core_liveness(
    transport: CommandFeedTransport,
    endpoint: CoreEndpoint,
) -> None:
    response = transport(
        CommandFeedHttpRequest(
            method="GET",
            url=f"{endpoint.base_url}/health/live",
            headers={"Accept": "application/json"},
            timeout_seconds=5.0,
        )
    )
    if (
        not isinstance(response, CommandFeedHttpResponse)
        or response.status != 200
        or len(response.body) > 16_384
    ):
        raise DumbMoneyWindowsServiceError("Core liveness probe failed")
    payload = _strict_json(response.body, "Core liveness")
    if payload != {"schema": HEALTH_SCHEMA, "status": "LIVE"}:
        raise DumbMoneyWindowsServiceError("Core liveness payload is invalid")


def _blocked_dispatch(reason: str) -> DumbMoneyCommandDispatch:
    return DumbMoneyCommandDispatch(
        desired_mode="PAUSED",
        kill_active=True,
        allow_new_risk=False,
        capital_authority=None,
        fail_closed_reason=reason,
        required_action="CANCEL_AND_RECONCILE",
        caught_up=False,
        next_sequence=0,
        next_digest="0" * 64,
        applied_event_ids=(),
    )


def _service_control(config_sha256: str) -> LiveBranchControl:
    return LiveBranchControl(
        schema_version=CONTROL_SCHEMA,
        mode="LIVE",
        account_label="agentic",
        official_mcp_endpoint=OFFICIAL_ROBINHOOD_MCP,
        live_branch_enabled=True,
        stock_execution_enabled=True,
        options_execution_enabled=False,
        paper_twin_required=True,
        no_day_trading_enforced=True,
        use_full_available_balance=False,
        unofficial_broker_api_allowed=False,
        owner_authorization_id=f"sealed-service:{config_sha256}",
    )


class _HealthServer:
    def __init__(self, state_reader: Callable[[], RunnerState]) -> None:
        state = state_reader

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health/live":
                    self._write(200, {"schema": HEALTH_SCHEMA, "status": "LIVE"})
                    return
                if self.path == "/health/ready":
                    snapshot = state()
                    ready = (
                        snapshot.health_status == "READY"
                        and snapshot.reconciled_once
                        and snapshot.execution_enabled
                        and snapshot.rollback_anchor_current
                    )
                    self._write(
                        200 if ready else 503,
                        {
                            "schema": HEALTH_SCHEMA,
                            "status": "READY" if ready else "NOT_READY",
                            "reason_codes": [] if ready else [snapshot.reason],
                        },
                    )
                    return
                self._write(404, {"schema": HEALTH_SCHEMA, "status": "NOT_FOUND"})

            def _write(self, status: int, payload: dict[str, Any]) -> None:
                encoded = canonical_json_bytes(payload)
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, _format: str, *_args: Any) -> None:
                return

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="DumbMoneyDopeyRobinhood-health",
            daemon=True,
        )

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5.0)


class DumbMoneyDopeyWindowsService:
    """Continuous reconcile-first supervisor with an at-most-once write sink."""

    def __init__(
        self,
        config: DopeyRunnerConfig,
        cell_token: str,
        robinhood_profile: str,
        *,
        transport: CommandFeedTransport,
        gateway: RobinhoodAgenticGateway,
        cycle_runner: Callable[..., dict[str, Any]] = run_live_branch_cycle,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        journal_anchor_factory: (
            Callable[[str], CoreJournalAnchorClient] | None
        ) = None,
    ) -> None:
        self.config = config
        self.cell_token = cell_token
        self.transport = transport
        self.gateway = gateway
        self.cycle_runner = cycle_runner
        self.clock = clock
        self._journal_anchor_factory = journal_anchor_factory or (
            lambda base_url: CoreJournalAnchorClient(
                base_url=base_url,
                transport=self.transport,
                cell_token_provider=lambda: self.cell_token,
                trusted_core_public_key=self.config.core_public_key,
                expected_account_hash=self.config.expected_account_hash,
                now_fn=self.clock,
            )
        )
        self.instance_id = str(uuid.uuid4())
        self._state = RunnerState()
        self._state_lock = threading.Lock()
        self._readiness_sequence = 0
        self._signer = _readiness_signer(cell_token)
        readiness_public = self._signer.public_key().public_bytes_raw()
        if (
            hashlib.sha256(readiness_public).hexdigest()
            != config.readiness_signer_public_key_sha256
        ):
            raise DumbMoneyWindowsServiceError(
                "cell credential does not bind the pinned readiness signer"
            )
        if not robinhood_profile:
            raise DumbMoneyWindowsServiceError(
                "Robinhood Credential Manager profile is absent"
            )
        self._health_server = _HealthServer(self.state)

    def state(self) -> RunnerState:
        with self._state_lock:
            return RunnerState(**self._state.__dict__)

    def _set_state(self, **changes: Any) -> None:
        with self._state_lock:
            for field, value in changes.items():
                setattr(self._state, field, value)

    def start(self) -> None:
        self.config.data_root.mkdir(parents=True, exist_ok=True)
        self.config.readiness_path.parent.mkdir(parents=True, exist_ok=True)
        self._health_server.start()
        self.write_readiness()

    def close(self) -> None:
        self._health_server.close()

    def write_readiness(self) -> dict[str, Any]:
        now = self.clock().astimezone(timezone.utc)
        valid_until = now + timedelta(seconds=self.config.readiness_ttl_seconds)
        snapshot = self.state()
        self._readiness_sequence += 1
        body: dict[str, Any] = {
            "schema": CORE_READINESS_SCHEMA,
            "service_name": SERVICE_NAME,
            "release_id": self.config.release_id,
            "instance_id": self.instance_id,
            "process_id": os.getpid(),
            "generation": self._readiness_sequence,
            "observed_at": _format_utc(now),
            "valid_until": _format_utc(valid_until),
            "endpoint": {
                "transport": "http",
                "host": "127.0.0.1",
                "port": self._health_server.port,
                "base_path": "/",
            },
            "fund_lock_sha256": self.config.fund_lock_sha256,
            "service_manifest_sha256": self.config.service_manifest_sha256,
            "authority": {
                "broker": "ROBINHOOD",
                "mode": snapshot.mode,
                "execution_enabled": snapshot.execution_enabled,
            },
            "health": {
                "status": snapshot.health_status,
                "reason_codes": [snapshot.reason],
                "core_ready": snapshot.core_ready,
                "reconciled_once": snapshot.reconciled_once,
                "last_cycle_status": snapshot.last_cycle_status,
                "command_sequence": snapshot.command_sequence,
                "command_digest": snapshot.command_digest,
                "rollback_anchor_current": snapshot.rollback_anchor_current,
                "runner_config_sha256": self.config.config_sha256,
                "readiness_public_key_sha256": (
                    self.config.readiness_signer_public_key_sha256
                ),
                "codex_executable_sha256": (self.config.codex_executable_sha256),
                "codex_local_provider": LOCAL_MODEL_PROVIDER,
                "codex_local_model": self.config.codex_local_model,
                "codex_local_model_digest": (self.config.codex_local_model_digest),
                "ollama_executable_sha256": (self.config.ollama_executable_sha256),
                "ollama_process_identity_sid": (
                    self.config.ollama_process_identity_sid
                ),
                "ollama_runtime_evidence_sha256": (
                    self.config.ollama_runtime_evidence_sha256
                ),
            },
            "capabilities": [
                "authenticated-promotion-resolution",
                "broker-reconciliation",
                "cell-command-checkpoints",
                "core-journal-head-anchors",
                "single-at-most-once-mcp-boundary",
            ],
        }
        unsigned: dict[str, Any] = {
            "schema": SIGNED_ENVELOPE_SCHEMA,
            "source_id": SERVICE_NAME,
            "source_sequence": self._readiness_sequence,
            "correlation_id": f"readiness-{self.instance_id}",
            "causation_id": None,
            "nonce": hashlib.sha256(
                canonical_json_bytes(
                    {
                        "instance_id": self.instance_id,
                        "sequence": self._readiness_sequence,
                        "observed_at": body["observed_at"],
                    }
                )
            ).hexdigest(),
            "not_before": body["observed_at"],
            "expires_at": body["valid_until"],
            "body_schema": CORE_READINESS_SCHEMA,
            "body_digest": hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
            "body": body,
            "signature_algorithm": "Ed25519",
            "signer_key_id": (self.config.readiness_signer_public_key_sha256),
        }
        unsigned["event_id"] = hashlib.sha256(
            canonical_json_bytes(unsigned)
        ).hexdigest()
        signature = self._signer.sign(canonical_json_bytes(unsigned))
        envelope = {
            **unsigned,
            "signature": base64.urlsafe_b64encode(signature)
            .decode("ascii")
            .rstrip("="),
        }
        _atomic_write_json(self.config.readiness_path, envelope)
        return envelope

    def _anchor_local_state(self, client: CoreJournalAnchorClient) -> None:
        try:
            command_sequence, command_digest = command_feed_head(
                self.config.data_root / "control" / "command-feed-state.v1.json"
            )
            live_records = read_ledger(ledger_path(self.config.data_root))
            paper_records = read_ledger(paper_twin_path(self.config.data_root))
        except (DumbMoneyCommandFeedError, LiveBranchLedgerError) as error:
            raise JournalAnchorError(
                "local journal integrity verification failed"
            ) from error
        heads = (
            (
                "command-feed",
                COMMAND_STATE_SCHEMA,
                command_sequence,
                command_digest,
            ),
            (
                "live-branch-ledger",
                LEDGER_SCHEMA,
                len(live_records),
                (
                    str(live_records[-1]["record_hash"])
                    if live_records
                    else GENESIS_HASH
                ),
            ),
            (
                "paper-twin-ledger",
                LEDGER_SCHEMA,
                len(paper_records),
                (
                    str(paper_records[-1]["record_hash"])
                    if paper_records
                    else GENESIS_HASH
                ),
            ),
        )
        for name, schema, sequence, digest in heads:
            client.anchor(
                journal_name=name,
                journal_schema=schema,
                journal_sequence=sequence,
                journal_head_sha256=digest,
            )

    def run_once(self) -> dict[str, Any]:
        now = self.clock().astimezone(timezone.utc)
        command_refresh: Callable[[datetime], DumbMoneyCommandDispatch] | None = None
        promotion_resolver: DumbMoneyContractResolverClient | None = None
        journal_anchor_client: CoreJournalAnchorClient | None = None
        core_ready = False
        try:
            endpoint = _core_endpoint_from_readiness(self.config, now)
            _core_liveness(self.transport, endpoint)
            journal_anchor_client = self._journal_anchor_factory(endpoint.base_url)
            self._anchor_local_state(journal_anchor_client)
            command_client = DumbMoneyCommandFeedClient(
                base_url=endpoint.base_url,
                cell_bearer_provider=lambda: self.cell_token,
                trusted_public_key=self.config.core_public_key,
                trusted_operator_public_keys=self.config.operator_public_keys,
                expected_account_hash=self.config.expected_account_hash,
                state_path=(
                    self.config.data_root / "control" / "command-feed-state.v1.json"
                ),
                transport=self.transport,
            )
            dispatch = command_client.poll_once(now)
            self._anchor_local_state(journal_anchor_client)
            command_refresh = command_client.poll_once
            promotion_resolver = DumbMoneyContractResolverClient(
                base_url=endpoint.base_url,
                cell_bearer_provider=lambda: self.cell_token,
                trusted_core_public_key=self.config.core_public_key,
                trusted_promoter_public_keys=self.config.promoter_public_keys,
                trusted_research_public_keys=self.config.research_public_keys,
                trusted_evaluator_public_keys=self.config.evaluator_public_keys,
                transport=self.transport,
            )
            core_ready = (
                dispatch.caught_up
                and dispatch.required_action == "APPLY_SIGNED_CONTROLS"
            )
        except JournalAnchorError as error:
            self._set_state(
                mode=START_MODE,
                health_status="BLOCKED",
                reason=f"rollback_anchor_rejected:{type(error).__name__}",
                core_ready=False,
                reconciled_once=False,
                execution_enabled=False,
                last_cycle_status="blocked_rollback_anchor",
                rollback_anchor_current=False,
            )
            self.write_readiness()
            return {
                "cycle_status": "blocked_rollback_anchor",
                "orders": [],
                "broker_contacted": False,
            }
        except Exception as error:
            dispatch = _blocked_dispatch(
                f"core_readiness_or_transport_failed:{type(error).__name__}"
            )
        prior = self.state()
        execute_orders = (
            prior.reconciled_once
            and prior.rollback_anchor_current
            and core_ready
            and dispatch.allow_new_risk
            and not dispatch.kill_active
            and command_refresh is not None
            and promotion_resolver is not None
        )
        result = self.cycle_runner(
            self.config.data_root,
            self.gateway,
            now,
            execute_orders,
            dumbmoney_controls=dispatch,
            dumbmoney_control_refresh=command_refresh,
            dumbmoney_promotion_resolver=promotion_resolver,
            authority_clock=self.clock,
            live_branch_control=_service_control(self.config.config_sha256),
        )
        rollback_anchor_current = False
        rollback_anchor_error = ""
        if journal_anchor_client is not None:
            try:
                self._anchor_local_state(journal_anchor_client)
                rollback_anchor_current = True
            except JournalAnchorError as error:
                rollback_anchor_error = (
                    f"rollback_anchor_rejected:{type(error).__name__}"
                )
        cycle_status = str(result.get("cycle_status", ""))
        preflight_reconciled = (
            cycle_status == "preflight_complete"
            and not result.get("order_history_blocker")
            and isinstance(result.get("account"), dict)
            and result["account"].get("authenticated") is True
            and result["account"].get("account_hash")
            == self.config.expected_account_hash
        )
        ambiguous_or_cancel = (
            "ambiguous" in cycle_status
            or cycle_status.startswith("cancel_only")
            or any(
                "ambiguous" in str(order.get("status", ""))
                for order in result.get("orders", [])
                if isinstance(order, dict)
            )
        )
        reconciled = (
            False
            if ambiguous_or_cancel
            else prior.reconciled_once or preflight_reconciled
        )
        execution_enabled = (
            reconciled
            and core_ready
            and rollback_anchor_current
            and dispatch.allow_new_risk
            and not dispatch.kill_active
            and not ambiguous_or_cancel
        )
        healthy_statuses = {
            "complete",
            "market_closed_monitoring_complete",
            "preflight_complete",
        }
        health_status = (
            "READY"
            if execution_enabled and cycle_status in healthy_statuses
            else "BLOCKED"
            if rollback_anchor_error
            else "DEGRADED"
        )
        reason = (
            rollback_anchor_error
            if rollback_anchor_error
            else "ALL_CURRENT_CONTROLS_ALLOW"
            if execution_enabled
            else dispatch.fail_closed_reason
            or cycle_status
            or "RECONCILIATION_REQUIRED"
        )
        self._set_state(
            mode="AGGRESSIVE_BOUNDED" if execution_enabled else START_MODE,
            health_status=health_status,
            reason=reason,
            core_ready=core_ready,
            reconciled_once=reconciled,
            execution_enabled=execution_enabled,
            last_cycle_status=cycle_status or "unknown",
            command_sequence=dispatch.next_sequence,
            command_digest=dispatch.next_digest,
            rollback_anchor_current=rollback_anchor_current,
        )
        self.write_readiness()
        return result

    def run_forever(self, stop_event: threading.Event) -> None:
        self.start()
        try:
            while not stop_event.is_set():
                if stop_event.wait(self.config.poll_interval_seconds):
                    break
                try:
                    self.run_once()
                except Exception as error:
                    self._set_state(
                        mode=START_MODE,
                        health_status="BLOCKED",
                        reason=f"cycle_failed_closed:{type(error).__name__}",
                        core_ready=False,
                        reconciled_once=False,
                        execution_enabled=False,
                        last_cycle_status="cycle_failed_closed",
                        rollback_anchor_current=False,
                    )
                    self.write_readiness()
        finally:
            self.close()


def _format_utc(value: datetime) -> str:
    utc = value.astimezone(timezone.utc)
    rendered = utc.isoformat(timespec="microseconds" if utc.microsecond else "seconds")
    return rendered.replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    encoded = canonical_json_bytes(payload) + b"\n"
    try:
        with temporary.open("xb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


class _DataRootLease:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> "_DataRootLease":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+b")
        try:
            self.handle.seek(0)
            import msvcrt

            msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
        except (OSError, ImportError) as error:
            self.handle.close()
            raise DumbMoneyWindowsServiceError(
                "another Dopey service owns the ProgramData root"
            ) from error
        return self

    def __exit__(self, *_args: Any) -> None:
        if self.handle is None or self.handle.closed:
            return
        try:
            self.handle.seek(0)
            import msvcrt

            msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self.handle.close()


def _program_data_path() -> Path:
    value = os.environ.get("PROGRAMDATA", "")
    if not value:
        raise DumbMoneyWindowsServiceError(
            "PROGRAMDATA is required for the sealed Windows service"
        )
    path = Path(value).resolve()
    if not path.is_absolute():
        raise DumbMoneyWindowsServiceError("PROGRAMDATA must be absolute")
    return path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=SERVICE_NAME,
        description="Sealed DumbMoney Robinhood venue-cell service",
        allow_abbrev=False,
    )
    parser.add_argument("--core-endpoint-ref", required=True)
    parser.add_argument("--core-cell-token-target", required=True)
    parser.add_argument("--robinhood-profile-target", required=True)
    parser.add_argument("--start-mode", required=True)
    parser.add_argument("--readiness-ref", required=True)
    parser.add_argument("--config-sha256", required=True)
    return parser


def _validate_cli(arguments: argparse.Namespace) -> None:
    expected = {
        "core_endpoint_ref": CORE_ENDPOINT_REF,
        "core_cell_token_target": CELL_TOKEN_TARGET_REF,
        "robinhood_profile_target": ROBINHOOD_PROFILE_TARGET_REF,
        "start_mode": START_MODE,
        "readiness_ref": READINESS_REF,
    }
    for field, value in expected.items():
        if getattr(arguments, field) != value:
            raise DumbMoneyWindowsServiceError(
                f"sealed service argument mismatch: {field}"
            )
    _digest(arguments.config_sha256, "--config-sha256")


def main(argv: list[str] | None = None) -> int:
    """Synchronous PyInstaller-compatible service entry point."""

    try:
        arguments = _parser().parse_args(argv)
        _validate_cli(arguments)
        program_data = _program_data_path()
        config_path = (program_data / CONFIG_RELATIVE_PATH).resolve()
        config = load_runner_config(
            config_path,
            arguments.config_sha256,
            program_data,
        )
        cell_token, robinhood_profile = load_secrets(WindowsCredentialManager())
        parent_mcp = DeterministicRobinhoodMcpClient(
            robinhood_profile,
            config.expected_account_hash,
        )
        gateway = RobinhoodAgenticGateway(
            subprocess.run,
            60,
            write_timeout_seconds=30,
            temporary_root=config.data_root / "temp",
            codex_executable_path=config.codex_executable_path,
            codex_executable_sha256=config.codex_executable_sha256,
            local_model=config.codex_local_model,
            local_model_verifier=PinnedOllamaModelVerifier(
                config.codex_local_model,
                config.codex_local_model_digest,
                config.ollama_executable_path,
                config.ollama_executable_sha256,
                config.ollama_process_identity_sid,
                config.data_root / OLLAMA_EVIDENCE_RELATIVE_PATH,
                config.ollama_runtime_evidence_sha256,
                LoopbackHttpTransport(),
            ),
            expected_account_hash=config.expected_account_hash,
            deterministic_mcp_call=parent_mcp,
        )
        service = DumbMoneyDopeyWindowsService(
            config,
            cell_token,
            robinhood_profile,
            transport=LoopbackHttpTransport(),
            gateway=gateway,
        )
        stop_event = threading.Event()

        def stop(_signum: int, _frame: Any) -> None:
            stop_event.set()

        for signal_name in ("SIGINT", "SIGTERM"):
            candidate = getattr(signal, signal_name, None)
            if candidate is not None:
                signal.signal(candidate, stop)
        with _DataRootLease(config.data_root / "service.lock"):
            service.run_forever(stop_event)
        return 0
    except KeyboardInterrupt:
        return 0
    except (DumbMoneyWindowsServiceError, OSError, ValueError) as error:
        print(
            f"{SERVICE_NAME} failed closed: {type(error).__name__}",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
