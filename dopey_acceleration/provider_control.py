"""User-scoped LLM provider and paper-research routing control."""

from __future__ import annotations

import ctypes
import json
import os
import tempfile
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Final, Literal, TypedDict, cast


ProviderId = Literal["openrouter", "openrouter_hybrid", "claude", "codex"]
InstrumentMode = Literal["stocks", "options", "both"]
ModelRole = Literal["evidence_mapper", "hypothesis_scout", "adversarial_auditor", "final_adjudicator"]
RoutingStage = Literal["parallel_discovery", "deep_review", "synthesis"]


class ProviderFlags(TypedDict):
    openrouter: bool
    openrouter_hybrid: bool
    claude: bool
    codex: bool


class ActiveModelRoute(TypedDict):
    route_id: str
    model_id: str
    role: ModelRole
    stage: RoutingStage
    provider: Literal["openrouter"]


class RoutingPolicy(TypedDict):
    provider: Literal["openrouter"]
    route_id: str
    strategy: str
    stage_order: list[RoutingStage]
    all_model_stages_required: bool
    fallback_allowed: bool
    independent_external_routes_allowed: bool


class ProviderControl(TypedDict):
    schema_version: str
    updated_utc: str
    instrument_mode: InstrumentMode
    providers: ProviderFlags
    paper_only: bool
    live_blocked: bool


SCHEMA_VERSION: Final[str] = "dopey-provider-control-v1"
PROVIDER_IDS: Final[tuple[ProviderId, ...]] = (
    "openrouter",
    "openrouter_hybrid",
    "claude",
    "codex",
)
INSTRUMENT_MODES: Final[tuple[InstrumentMode, ...]] = ("stocks", "options", "both")
SECRET_FILENAME: Final[str] = "openrouter_api_key.dpapi"
CONFIG_FILENAME: Final[str] = "provider_control.json"
DPAPI_DESCRIPTION: Final[str] = "DOPEY OpenRouter API key"
CRYPTPROTECT_UI_FORBIDDEN: Final[int] = 0x1
ACTIVE_HYBRID_ROUTE_ID: Final[str] = "openrouter_four_model_hybrid"
ACTIVE_MODEL_ROSTER: Final[tuple[ActiveModelRoute, ...]] = (
    {
        "route_id": "openrouter_gemini_3_6_flash",
        "model_id": "google/gemini-3.6-flash",
        "role": "evidence_mapper",
        "stage": "parallel_discovery",
        "provider": "openrouter",
    },
    {
        "route_id": "openrouter_luna_5_6",
        "model_id": "openai/gpt-5.6-luna",
        "role": "hypothesis_scout",
        "stage": "parallel_discovery",
        "provider": "openrouter",
    },
    {
        "route_id": "openrouter_glm_5_2",
        "model_id": "z-ai/glm-5.2",
        "role": "adversarial_auditor",
        "stage": "deep_review",
        "provider": "openrouter",
    },
    {
        "route_id": "openrouter_claude_sonnet_5",
        "model_id": "anthropic/claude-sonnet-5",
        "role": "final_adjudicator",
        "stage": "synthesis",
        "provider": "openrouter",
    },
)


class ProviderControlError(RuntimeError):
    """Raised when provider control cannot preserve its local safety contract."""


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _runtime_root() -> Path:
    override = os.environ.get("DOPEY_PROVIDER_CONTROL_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        raise ProviderControlError("LOCALAPPDATA is required for user-scoped DOPEY provider control")
    return (Path(local_app_data) / "ObtuseAI" / "DOPEY").resolve()


def _config_path() -> Path:
    return _runtime_root() / CONFIG_FILENAME


def _secret_path() -> Path:
    return _runtime_root() / "secrets" / SECRET_FILENAME


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provider_flags(openrouter_enabled: bool) -> ProviderFlags:
    return {
        "openrouter": openrouter_enabled,
        "openrouter_hybrid": openrouter_enabled,
        "claude": False,
        "codex": False,
    }


def _active_model_roster() -> list[ActiveModelRoute]:
    return [dict(route) for route in ACTIVE_MODEL_ROSTER]


def _routing_policy() -> RoutingPolicy:
    return {
        "provider": "openrouter",
        "route_id": ACTIVE_HYBRID_ROUTE_ID,
        "strategy": "four_model_role_routed_conservative_adjudication",
        "stage_order": ["parallel_discovery", "deep_review", "synthesis"],
        "all_model_stages_required": True,
        "fallback_allowed": False,
        "independent_external_routes_allowed": False,
    }


def active_model_roster() -> list[ActiveModelRoute]:
    return _active_model_roster()


def routing_policy() -> RoutingPolicy:
    return _routing_policy()


def _default_control() -> ProviderControl:
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_utc": _utc_now(),
        "instrument_mode": "both",
        "providers": _provider_flags(True),
        "paper_only": True,
        "live_blocked": True,
    }


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, record: ProviderControl) -> None:
    payload = json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8") + b"\n"
    _atomic_write_bytes(path, payload)


def _validated_provider_flags(value: object) -> ProviderFlags:
    if not isinstance(value, dict):
        raise ProviderControlError("provider control providers field must be an object")
    raw_flags: dict[str, bool] = {}
    for provider in PROVIDER_IDS:
        enabled = value.get(provider)
        if type(enabled) is not bool:
            raise ProviderControlError(
                f"provider control flag must be boolean: provider={provider}, actual={enabled!r}"
            )
        raw_flags[provider] = cast(bool, enabled)
    if raw_flags["openrouter_hybrid"] and not raw_flags["openrouter"]:
        raise ProviderControlError("OpenRouter hybrid cannot be enabled while OpenRouter is disabled")
    return cast(ProviderFlags, raw_flags)


def _validated_control(value: object) -> ProviderControl:
    if not isinstance(value, dict):
        raise ProviderControlError("provider control must be a JSON object")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ProviderControlError(
            "provider control schema is unsupported: "
            f"actual={value.get('schema_version')!r}, required={SCHEMA_VERSION!r}"
        )
    instrument_mode = value.get("instrument_mode")
    if instrument_mode not in INSTRUMENT_MODES:
        raise ProviderControlError(f"provider control instrument mode is invalid: {instrument_mode!r}")
    provider_flags = _validated_provider_flags(value.get("providers"))
    if value.get("paper_only") is not True or value.get("live_blocked") is not True:
        raise ProviderControlError("provider control must assert paper_only=true and live_blocked=true")
    updated_utc = value.get("updated_utc")
    if not isinstance(updated_utc, str) or not updated_utc.strip():
        raise ProviderControlError("provider control updated_utc must be a non-empty string")
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_utc": updated_utc,
        "instrument_mode": cast(InstrumentMode, instrument_mode),
        "providers": provider_flags,
        "paper_only": True,
        "live_blocked": True,
    }


def load_provider_control() -> ProviderControl:
    path = _config_path()
    if not path.exists():
        control = _default_control()
        _atomic_write_json(path, control)
        return control
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProviderControlError(f"provider control is unreadable: path={path}, error={error}") from error
    return _validated_control(value)


def set_provider_enabled(provider: str, enabled: bool) -> ProviderControl:
    if provider not in PROVIDER_IDS:
        raise ValueError(f"unsupported LLM provider control: provider={provider!r}")
    if type(enabled) is not bool:
        raise TypeError(f"provider enabled state must be bool: actual={type(enabled).__name__}")
    if provider in {"claude", "codex"}:
        raise ValueError(
            f"independent provider route is retired; use the governed OpenRouter four-model hybrid: provider={provider!r}"
        )
    current = load_provider_control()
    candidate: ProviderControl = {
        **current,
        "updated_utc": _utc_now(),
        "providers": _provider_flags(enabled),
    }
    validated = _validated_control(candidate)
    if validated["providers"]["openrouter"]:
        credential = openrouter_credential_status()
        if credential["usable"] is not True:
            raise ProviderControlError(
                "OpenRouter cannot be enabled until the user-scoped API key is configured and usable: "
                f"configured={credential['configured']}, validation_status={credential['validation_status']}"
            )
    _atomic_write_json(_config_path(), validated)
    return validated


def set_instrument_mode(instrument_mode: str) -> ProviderControl:
    if instrument_mode not in INSTRUMENT_MODES:
        raise ValueError(
            f"unsupported paper-research instrument mode: actual={instrument_mode!r}, allowed={INSTRUMENT_MODES}"
        )
    current = load_provider_control()
    candidate: ProviderControl = {
        **current,
        "updated_utc": _utc_now(),
        "instrument_mode": cast(InstrumentMode, instrument_mode),
    }
    validated = _validated_control(candidate)
    _atomic_write_json(_config_path(), validated)
    return validated


def _bytes_blob(payload: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
    buffer = ctypes.create_string_buffer(payload)
    pointer = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    return _DataBlob(len(payload), pointer), buffer


def _protect_secret(payload: bytes) -> bytes:
    if os.name != "nt":
        raise ProviderControlError("OpenRouter credential storage requires Windows DPAPI")
    input_blob, input_buffer = _bytes_blob(payload)
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    result = crypt32.CryptProtectData(
        ctypes.byref(input_blob),
        DPAPI_DESCRIPTION,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    )
    if result == 0:
        raise ProviderControlError(f"Windows DPAPI encryption failed: winerror={ctypes.get_last_error()}")
    del input_buffer
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _unprotect_secret(payload: bytes) -> bytes:
    if os.name != "nt":
        raise ProviderControlError("OpenRouter credential storage requires Windows DPAPI")
    input_blob, input_buffer = _bytes_blob(payload)
    output_blob = _DataBlob()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    result = crypt32.CryptUnprotectData(
        ctypes.byref(input_blob),
        None,
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(output_blob),
    )
    if result == 0:
        raise ProviderControlError(f"Windows DPAPI decryption failed: winerror={ctypes.get_last_error()}")
    del input_buffer
    try:
        return ctypes.string_at(output_blob.pbData, output_blob.cbData)
    finally:
        kernel32.LocalFree(output_blob.pbData)


def _validated_api_key(api_key: str) -> str:
    if not isinstance(api_key, str):
        raise TypeError(f"OpenRouter API key must be a string: actual={type(api_key).__name__}")
    normalized = api_key.strip()
    if len(normalized) < 20:
        raise ValueError("OpenRouter API key is too short")
    if any(character.isspace() for character in normalized):
        raise ValueError("OpenRouter API key must not contain whitespace")
    return normalized


def store_openrouter_api_key(api_key: str) -> dict[str, object]:
    normalized = _validated_api_key(api_key)
    encrypted = _protect_secret(normalized.encode("utf-8"))
    _atomic_write_bytes(_secret_path(), encrypted)
    verified = _unprotect_secret(_secret_path().read_bytes()).decode("utf-8")
    if verified != normalized:
        raise ProviderControlError("OpenRouter API key verification failed after encrypted storage")
    return openrouter_credential_status()


def _user_environment_key() -> str:
    if os.name != "nt":
        return ""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _ = winreg.QueryValueEx(key, "OPENROUTER_API_KEY")
    except FileNotFoundError:
        return ""
    return value.strip() if isinstance(value, str) else ""


def resolve_openrouter_api_key() -> str:
    secret_path = _secret_path()
    if secret_path.exists():
        try:
            decrypted = _unprotect_secret(secret_path.read_bytes()).decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise ProviderControlError(
                f"encrypted OpenRouter API key is unreadable: path={secret_path}, error={error}"
            ) from error
        return _validated_api_key(decrypted)
    process_value = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if process_value:
        return _validated_api_key(process_value)
    user_value = _user_environment_key()
    if user_value:
        return _validated_api_key(user_value)
    raise ProviderControlError("OpenRouter API key is not configured for the current Windows user")


def openrouter_credential_status() -> dict[str, object]:
    secret_path = _secret_path()
    process_value = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if secret_path.exists():
        source = "windows_dpapi_user_scope"
        configured = True
        try:
            updated_utc = datetime.fromtimestamp(secret_path.stat().st_mtime, timezone.utc).isoformat()
        except OSError:
            updated_utc = None
        decrypted = ""
        try:
            decrypted = _unprotect_secret(secret_path.read_bytes()).decode("utf-8")
            _validated_api_key(decrypted)
        except (OSError, UnicodeError, ValueError, ProviderControlError):
            usable = False
        else:
            usable = True
        finally:
            decrypted = ""
    elif process_value:
        source = "process_environment"
        configured = True
        updated_utc = None
        try:
            _validated_api_key(process_value)
        except ValueError:
            usable = False
        else:
            usable = True
    else:
        user_value = _user_environment_key()
        updated_utc = None
        if user_value:
            source = "user_environment"
            configured = True
            try:
                _validated_api_key(user_value)
            except ValueError:
                usable = False
            else:
                usable = True
        else:
            source = "unconfigured"
            configured = False
            usable = False
    validation_status = "validated_usable" if usable else "unconfigured" if not configured else "configured_unusable"
    return {
        "configured": configured,
        "usable": usable,
        "validation_status": validation_status,
        "source": source,
        "updated_utc": updated_utc,
        "plaintext_exposed": False,
        "repository_storage": False,
    }


def provider_control_state() -> dict[str, object]:
    control = load_provider_control()
    credential = openrouter_credential_status()
    openrouter_available = credential["usable"] is True
    legacy_provider_flags = dict(control["providers"])
    active_route_enabled = (
        control["providers"]["openrouter"] and control["providers"]["openrouter_hybrid"]
    )
    return {
        **control,
        "providers": _provider_flags(active_route_enabled),
        "legacy_provider_flags": legacy_provider_flags,
        "active_model_roster": _active_model_roster(),
        "routing_policy": _routing_policy(),
        "credential": credential,
        "availability": {
            "openrouter": openrouter_available,
            "openrouter_hybrid": openrouter_available,
            "claude": False,
            "codex": False,
        },
        "active_route_available": openrouter_available and active_route_enabled,
        "api_key_value_exposed": False,
    }
