from __future__ import annotations

import base64
import hashlib
import json
import multiprocessing
import os
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import dopey_live.dumbmoney_windows_service as windows_service
from dopey_live.dumbmoney_authority import (
    _verify_signed_wrapper,
    canonical_json_bytes,
)
from dopey_live.dumbmoney_command_feed import (
    CommandFeedHttpResponse,
    DumbMoneyCommandDispatch,
)
from dopey_live.dumbmoney_journal_anchor import JournalAnchorError
from dopey_live.dumbmoney_windows_service import (
    CELL_TOKEN_TARGET_REF,
    CONFIG_RELATIVE_PATH,
    CORE_ENDPOINT_REF,
    CORE_READINESS_SCHEMA,
    READINESS_REF,
    ROBINHOOD_PROFILE_TARGET_REF,
    START_MODE,
    CoreEndpoint,
    DopeyRunnerConfig,
    DumbMoneyDopeyWindowsService,
    DumbMoneyWindowsServiceError,
    PinnedOllamaModelVerifier,
    _core_endpoint_from_readiness,
    _DataRootLease,
    _readiness_signer,
    _windows_loopback_listener_owner,
    load_runner_config,
    load_secrets,
)
from dopey_live.robinhood_gateway import (
    RobinhoodAgenticGateway,
    RobinhoodGatewayError,
    _codex_exec_command,
)

NOW = datetime(2099, 1, 1, 0, 0, 30, tzinfo=timezone.utc)
CELL_TOKEN = "cell-token-from-windows-credential-manager"
PROFILE = "robinhood-profile-from-windows-credential-manager"
OLLAMA_SID = "S-1-5-21-1-2-3-1001"


def _probe_data_root_lease(path: str, queue: Any) -> None:
    try:
        with _DataRootLease(Path(path)):
            queue.put("acquired")
    except DumbMoneyWindowsServiceError:
        queue.put("blocked")


def _format_utc(value: datetime) -> str:
    return (
        value.astimezone(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def _key_entry(
    private_key: Ed25519PrivateKey,
) -> tuple[str, str, bytes]:
    public_key = private_key.public_key().public_bytes_raw()
    key_id = hashlib.sha256(public_key).hexdigest()
    encoded = base64.urlsafe_b64encode(public_key).decode().rstrip("=")
    return key_id, encoded, public_key


def _config_payload(
    program_data: Path,
    core_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    core_id, core_encoded, _ = _key_entry(core_key)
    del core_id
    operator_id, operator_encoded, _ = _key_entry(Ed25519PrivateKey.generate())
    promoter_id, promoter_encoded, _ = _key_entry(Ed25519PrivateKey.generate())
    research_id, research_encoded, _ = _key_entry(Ed25519PrivateKey.generate())
    evaluator_id, evaluator_encoded, _ = _key_entry(Ed25519PrivateKey.generate())
    readiness_public = _readiness_signer(CELL_TOKEN).public_key().public_bytes_raw()
    executable_path = Path(sys.executable).resolve()
    return {
        "schema": "dopey.dumbmoney-robinhood-runner-config.v1",
        "service_name": "DumbMoneyDopeyRobinhood",
        "release_id": "dumbmoney-test-release",
        "core_endpoint_ref": CORE_ENDPOINT_REF,
        "core_readiness_path": str(
            program_data / "DumbMoney" / "readiness" / "DumbMoneyCore.json"
        ),
        "core_cell_token_target": CELL_TOKEN_TARGET_REF,
        "robinhood_profile_target": ROBINHOOD_PROFILE_TARGET_REF,
        "start_mode": START_MODE,
        "data_root": str(program_data / "DumbMoney" / "dopey-robinhood"),
        "readiness_ref": READINESS_REF,
        "readiness_path": str(
            program_data / "DumbMoney" / "readiness" / "DumbMoneyDopeyRobinhood.json"
        ),
        "core_public_key_base64url": core_encoded,
        "operator_public_keys_base64url": {
            operator_id: operator_encoded,
        },
        "promoter_public_keys_base64url": {
            promoter_id: promoter_encoded,
        },
        "research_public_keys_base64url": {
            research_id: research_encoded,
        },
        "evaluator_public_keys_base64url": {
            evaluator_id: evaluator_encoded,
        },
        "expected_account_hash": "c" * 64,
        "fund_lock_sha256": "d" * 64,
        "service_manifest_sha256": "e" * 64,
        "role_public_keys_sha256": "f" * 64,
        "core_runner_config_sha256": "1" * 64,
        "risk_policy_sha256": "2" * 64,
        "readiness_signer_public_key_sha256": hashlib.sha256(
            readiness_public
        ).hexdigest(),
        "codex_executable_path": str(executable_path),
        "codex_executable_sha256": hashlib.sha256(
            executable_path.read_bytes()
        ).hexdigest(),
        "codex_local_provider": "ollama",
        "codex_local_model": "gpt-oss:20b",
        "codex_local_model_digest": "3" * 64,
        "ollama_executable_path": str(executable_path),
        "ollama_executable_sha256": hashlib.sha256(
            executable_path.read_bytes()
        ).hexdigest(),
        "ollama_process_identity_sid": OLLAMA_SID,
        "ollama_runtime_evidence_sha256": "4" * 64,
        "poll_interval_seconds": 15,
        "readiness_ttl_seconds": 90,
    }


def _write_config(
    program_data: Path,
    core_key: Ed25519PrivateKey,
) -> tuple[DopeyRunnerConfig, dict[str, Any]]:
    payload = _config_payload(program_data, core_key)
    path = program_data / CONFIG_RELATIVE_PATH
    path.parent.mkdir(parents=True)
    raw = canonical_json_bytes(payload) + b"\n"
    path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    return load_runner_config(path, digest, program_data), payload


def _signed_core_readiness(
    config: DopeyRunnerConfig,
    core_key: Ed25519PrivateKey,
) -> dict[str, Any]:
    body = {
        "schema": CORE_READINESS_SCHEMA,
        "service_name": "DumbMoneyCore",
        "release_id": config.release_id,
        "instance_id": "8c2df19e-a2dc-4ad4-9b37-c3f03b6c02c6",
        "process_id": 42,
        "generation": 0,
        "observed_at": _format_utc(NOW - timedelta(seconds=5)),
        "valid_until": _format_utc(NOW + timedelta(seconds=85)),
        "endpoint": {
            "transport": "http",
            "host": "127.0.0.1",
            "port": 49152,
            "base_path": "/",
        },
        "fund_lock_sha256": config.fund_lock_sha256,
        "service_manifest_sha256": config.service_manifest_sha256,
        "authority": {
            "broker": "NONE",
            "mode": "OFFLINE",
            "execution_enabled": False,
        },
        "health": {
            "status": "READY",
            "core_public_key_sha256": hashlib.sha256(
                config.core_public_key
            ).hexdigest(),
            "role_public_keys_sha256": config.role_public_keys_sha256,
            "runner_config_sha256": config.core_runner_config_sha256,
            "risk_policy_sha256": config.risk_policy_sha256,
        },
        "capabilities": ["cell-command-checkpoints", "event-ledger"],
    }
    unsigned: dict[str, Any] = {
        "schema": "dumbmoney.signed-envelope.v1",
        "source_id": "DumbMoneyCore",
        "source_sequence": 1,
        "correlation_id": "core-readiness-test",
        "causation_id": None,
        "nonce": "core-readiness-nonce-1",
        "not_before": body["observed_at"],
        "expires_at": body["valid_until"],
        "body_schema": CORE_READINESS_SCHEMA,
        "body_digest": hashlib.sha256(canonical_json_bytes(body)).hexdigest(),
        "body": body,
        "signature_algorithm": "Ed25519",
        "signer_key_id": hashlib.sha256(config.core_public_key).hexdigest(),
    }
    unsigned["event_id"] = hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    signature = core_key.sign(canonical_json_bytes(unsigned))
    return {
        **unsigned,
        "signature": base64.urlsafe_b64encode(signature).decode().rstrip("="),
    }


def test_public_config_is_exact_path_and_exact_raw_sha(
    tmp_path: Path,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    config, payload = _write_config(tmp_path, core_key)

    assert config.expected_account_hash == "c" * 64
    assert config.data_root == (tmp_path / "DumbMoney" / "dopey-robinhood").resolve()

    path = tmp_path / CONFIG_RELATIVE_PATH
    path.write_bytes(canonical_json_bytes({**payload, "release_id": "tampered"}))
    with pytest.raises(
        DumbMoneyWindowsServiceError,
        match="does not match --config-sha256",
    ):
        load_runner_config(path, config.config_sha256, tmp_path)


class FakeCredentials:
    def __init__(self) -> None:
        self.targets: list[str] = []

    def read_bytes(self, target: str) -> bytes:
        self.targets.append(target)
        if target == "DumbMoney/DopeyCellToken":
            return CELL_TOKEN.encode()
        if target == "DumbMoney/RobinhoodProfile":
            return PROFILE.encode()
        raise AssertionError("unexpected credential target")


def test_secrets_load_only_from_two_fixed_credential_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DUMBMONEY_DOPEY_CELL_TOKEN", "forbidden-env-token")
    monkeypatch.setenv("ROBINHOOD_PROFILE", "forbidden-env-profile")
    provider = FakeCredentials()

    assert load_secrets(provider) == (CELL_TOKEN, PROFILE)
    assert provider.targets == [
        "DumbMoney/DopeyCellToken",
        "DumbMoney/RobinhoodProfile",
    ]


def test_core_endpoint_requires_current_signed_pinned_readiness(
    tmp_path: Path,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    config, _ = _write_config(tmp_path, core_key)
    readiness = _signed_core_readiness(config, core_key)
    config.core_readiness_path.parent.mkdir(parents=True, exist_ok=True)
    config.core_readiness_path.write_bytes(canonical_json_bytes(readiness))

    endpoint = _core_endpoint_from_readiness(config, NOW)

    assert endpoint.base_url == "http://127.0.0.1:49152"
    tampered = json.loads(json.dumps(readiness))
    tampered["body"]["endpoint"]["host"] = "example.com"
    config.core_readiness_path.write_bytes(canonical_json_bytes(tampered))
    with pytest.raises(
        DumbMoneyWindowsServiceError,
        match="body digest mismatch",
    ):
        _core_endpoint_from_readiness(config, NOW)
    config.core_readiness_path.write_bytes(canonical_json_bytes(readiness))
    with pytest.raises(
        DumbMoneyWindowsServiceError,
        match="not currently valid",
    ):
        _core_endpoint_from_readiness(
            config,
            NOW + timedelta(minutes=2),
        )


class FakeCommandClient:
    dispatch: DumbMoneyCommandDispatch

    def __init__(self, **_kwargs: Any) -> None:
        pass

    def poll_once(self, _now: datetime) -> DumbMoneyCommandDispatch:
        return self.dispatch


class FakeResolver:
    def __init__(self, **_kwargs: Any) -> None:
        pass


class FakeJournalAnchor:
    def __init__(self, *, reject: bool = False) -> None:
        self.reject = reject
        self.calls: list[dict[str, Any]] = []

    def anchor(self, **kwargs: Any) -> None:
        self.calls.append(dict(kwargs))
        if self.reject:
            raise JournalAnchorError("Core rejected rolled-back journal")


def test_service_starts_reconciliation_only_then_allows_next_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    config, _ = _write_config(tmp_path, core_key)
    FakeCommandClient.dispatch = DumbMoneyCommandDispatch(
        desired_mode="LIVE",
        kill_active=False,
        allow_new_risk=True,
        capital_authority=None,
        fail_closed_reason="",
        required_action="APPLY_SIGNED_CONTROLS",
        caught_up=True,
        next_sequence=7,
        next_digest="7" * 64,
        applied_event_ids=(),
    )
    monkeypatch.setattr(
        windows_service,
        "_core_endpoint_from_readiness",
        lambda *_args: CoreEndpoint(
            "http://127.0.0.1:49152",
            "8c2df19e-a2dc-4ad4-9b37-c3f03b6c02c6",
            _format_utc(NOW),
            _format_utc(NOW + timedelta(seconds=90)),
        ),
    )
    monkeypatch.setattr(
        windows_service,
        "_core_liveness",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        windows_service,
        "DumbMoneyCommandFeedClient",
        FakeCommandClient,
    )
    monkeypatch.setattr(
        windows_service,
        "DumbMoneyContractResolverClient",
        FakeResolver,
    )
    execute_values: list[bool] = []
    anchor_client = FakeJournalAnchor()

    def cycle_runner(
        _root: Path,
        _gateway: object,
        _now: datetime,
        execute_orders: bool,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        execute_values.append(execute_orders)
        return {
            "cycle_status": "complete" if execute_orders else "preflight_complete",
            "order_history_blocker": "",
            "account": {
                "authenticated": True,
                "account_hash": config.expected_account_hash,
            },
            "orders": [],
        }

    service = DumbMoneyDopeyWindowsService(
        config,
        CELL_TOKEN,
        PROFILE,
        transport=lambda _request: (_ for _ in ()).throw(
            AssertionError("transport was monkeypatched away")
        ),
        gateway=object(),  # type: ignore[arg-type]
        cycle_runner=cycle_runner,
        clock=lambda: NOW,
        journal_anchor_factory=lambda _base_url: anchor_client,  # type: ignore[arg-type]
    )
    try:
        first = service.run_once()
        second = service.run_once()
        readiness = json.loads(config.readiness_path.read_text())
        verified = _verify_signed_wrapper(
            readiness,
            _readiness_signer(CELL_TOKEN).public_key().public_bytes_raw(),
            NOW,
            enforce_current_window=True,
        )
    finally:
        service._health_server.server.server_close()

    assert first["cycle_status"] == "preflight_complete"
    assert second["cycle_status"] == "complete"
    assert execute_values == [False, True]
    assert len(anchor_client.calls) == 18
    assert service.state().mode == "AGGRESSIVE_BOUNDED"
    assert service.state().rollback_anchor_current is True
    assert verified.body["authority"]["execution_enabled"] is True
    assert verified.body["health"]["command_sequence"] == 7
    assert verified.body["health"]["rollback_anchor_current"] is True


def test_rollback_anchor_rejection_blocks_before_broker_contact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    config, _ = _write_config(tmp_path, core_key)
    monkeypatch.setattr(
        windows_service,
        "_core_endpoint_from_readiness",
        lambda *_args: CoreEndpoint(
            "http://127.0.0.1:49152",
            "8c2df19e-a2dc-4ad4-9b37-c3f03b6c02c6",
            _format_utc(NOW),
            _format_utc(NOW + timedelta(seconds=90)),
        ),
    )
    monkeypatch.setattr(
        windows_service,
        "_core_liveness",
        lambda *_args: None,
    )
    cycle_calls: list[bool] = []
    anchor_client = FakeJournalAnchor(reject=True)
    service = DumbMoneyDopeyWindowsService(
        config,
        CELL_TOKEN,
        PROFILE,
        transport=lambda _request: (_ for _ in ()).throw(
            AssertionError("command transport must not run")
        ),
        gateway=object(),  # type: ignore[arg-type]
        cycle_runner=lambda *_args, **_kwargs: cycle_calls.append(True),  # type: ignore[arg-type]
        clock=lambda: NOW,
        journal_anchor_factory=lambda _base_url: anchor_client,  # type: ignore[arg-type]
    )
    try:
        result = service.run_once()
        readiness = json.loads(config.readiness_path.read_text())
    finally:
        service._health_server.server.server_close()

    assert result == {
        "cycle_status": "blocked_rollback_anchor",
        "orders": [],
        "broker_contacted": False,
    }
    assert cycle_calls == []
    assert service.state().health_status == "BLOCKED"
    assert service.state().rollback_anchor_current is False
    assert readiness["body"]["authority"]["execution_enabled"] is False
    assert readiness["body"]["health"]["rollback_anchor_current"] is False


def test_corrupt_local_journal_blocks_before_broker_contact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    config, _ = _write_config(tmp_path, core_key)
    command_state = config.data_root / "control" / "command-feed-state.v1.json"
    command_state.parent.mkdir(parents=True)
    command_state.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(
        windows_service,
        "_core_endpoint_from_readiness",
        lambda *_args: CoreEndpoint(
            "http://127.0.0.1:49152",
            "8c2df19e-a2dc-4ad4-9b37-c3f03b6c02c6",
            _format_utc(NOW),
            _format_utc(NOW + timedelta(seconds=90)),
        ),
    )
    monkeypatch.setattr(
        windows_service,
        "_core_liveness",
        lambda *_args: None,
    )
    cycle_calls: list[bool] = []
    anchor_client = FakeJournalAnchor()
    service = DumbMoneyDopeyWindowsService(
        config,
        CELL_TOKEN,
        PROFILE,
        transport=lambda _request: (_ for _ in ()).throw(
            AssertionError("command transport must not run")
        ),
        gateway=object(),  # type: ignore[arg-type]
        cycle_runner=lambda *_args, **_kwargs: cycle_calls.append(True),  # type: ignore[arg-type]
        clock=lambda: NOW,
        journal_anchor_factory=lambda _base_url: anchor_client,  # type: ignore[arg-type]
    )
    try:
        result = service.run_once()
    finally:
        service._health_server.server.server_close()

    assert result["cycle_status"] == "blocked_rollback_anchor"
    assert result["broker_contacted"] is False
    assert cycle_calls == []
    assert anchor_client.calls == []


def test_service_startup_writes_readiness_without_broker_call(
    tmp_path: Path,
) -> None:
    core_key = Ed25519PrivateKey.generate()
    config, _ = _write_config(tmp_path, core_key)
    cycle_calls: list[bool] = []
    service = DumbMoneyDopeyWindowsService(
        config,
        CELL_TOKEN,
        PROFILE,
        transport=lambda _request: (_ for _ in ()).throw(
            AssertionError("startup must not call Core")
        ),
        gateway=object(),  # type: ignore[arg-type]
        cycle_runner=lambda *_args, **_kwargs: cycle_calls.append(True),  # type: ignore[arg-type]
        clock=lambda: NOW,
    )

    service.start()
    service.close()

    assert cycle_calls == []
    readiness = json.loads(config.readiness_path.read_text())
    assert readiness["body"]["authority"] == {
        "broker": "ROBINHOOD",
        "mode": "RECONCILIATION_ONLY",
        "execution_enabled": False,
    }


def test_profile_is_in_memory_only_and_child_executable_is_sha_pinned(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="prohibited"):
        RobinhoodAgenticGateway(
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("test must not spawn a process")
            ),
            60,
            mcp_bearer_token=PROFILE,
        )

    executable = tmp_path / "codex.exe"
    executable.write_bytes(b"sealed-codex-fixture")
    executable_sha256 = hashlib.sha256(executable.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="prohibited"):
        RobinhoodAgenticGateway(
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("test must not spawn a process")
            ),
            60,
            mcp_bearer_token=PROFILE,
            codex_executable_path=executable,
            codex_executable_sha256=executable_sha256,
        )
    with pytest.raises(ValueError, match="prohibited"):
        _codex_exec_command(
            str(executable),
            str(tmp_path),
            tmp_path / "result.json",
            ("get_accounts",),
            "DUMBMONEY_ROBINHOOD_MCP_BEARER",
        )
    gateway = RobinhoodAgenticGateway(
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("test must not spawn a process")
        ),
        60,
        temporary_root=tmp_path / "temp",
        codex_executable_path=executable,
        codex_executable_sha256=executable_sha256,
        local_model="gpt-oss:20b",
        local_model_verifier=lambda: None,
        expected_account_hash="a" * 64,
        deterministic_mcp_call=(
            lambda _tool, _arguments, _timeout, _pre_call_guard: {}
        ),
    )
    command = _codex_exec_command(
        str(executable),
        str(tmp_path),
        tmp_path / "result.json",
        ("get_accounts",),
        None,
        "gpt-oss:20b",
    )

    joined_command = " ".join(command)
    assert PROFILE not in joined_command
    assert command[command.index("--local-provider") + 1] == "ollama"
    assert command[command.index("--model") + 1] == "gpt-oss:20b"
    assert "--oss" in command
    assert not any("openai" in value.lower() for value in command)
    assert "mcp_servers." not in joined_command
    assert "agent.robinhood.com" not in joined_command
    assert "DUMBMONEY_ROBINHOOD_MCP_BEARER" not in joined_command
    assert gateway._subprocess_env is None
    assert gateway._bearer_token_env_var is None

    executable.write_bytes(b"path-hijack")
    with pytest.raises(RobinhoodGatewayError, match="SHA-256 mismatch"):
        gateway._verify_codex_executable()


def test_pinned_ollama_model_is_verified_by_exact_local_inventory_digest(
    tmp_path: Path,
) -> None:
    calls: list[Any] = []
    executable_path = Path(sys.executable).resolve()
    executable_sha256 = hashlib.sha256(executable_path.read_bytes()).hexdigest()
    evidence_path = tmp_path / "ollama-runtime-evidence.v1.json"
    evidence_path.write_bytes(b'{"evidence_kind":"STATIC_INSTALLATION_ATTESTATION"}\n')
    evidence_sha256 = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    owner_calls: list[tuple[str, int]] = []

    def transport(request: Any) -> CommandFeedHttpResponse:
        calls.append(request)
        return CommandFeedHttpResponse(
            status=200,
            headers={"Content-Type": "application/json"},
            body=canonical_json_bytes(
                {
                    "models": [
                        {
                            "name": "gpt-oss:20b",
                            "model": "gpt-oss:20b",
                            "digest": "3" * 64,
                        }
                    ]
                }
            ),
        )

    def listener_owner(host: str, port: int) -> tuple[int, Path, str]:
        owner_calls.append((host, port))
        return 42, executable_path, OLLAMA_SID

    verifier = PinnedOllamaModelVerifier(
        "gpt-oss:20b",
        "3" * 64,
        executable_path,
        executable_sha256,
        OLLAMA_SID,
        evidence_path,
        evidence_sha256,
        transport,
        listener_owner,
    )
    verifier()

    assert len(calls) == 1
    assert owner_calls == [
        ("127.0.0.1", 11_434),
        ("127.0.0.1", 11_434),
    ]
    assert calls[0].url == "http://127.0.0.1:11434/api/tags"
    assert calls[0].method == "GET"

    wrong = PinnedOllamaModelVerifier(
        "gpt-oss:20b",
        "4" * 64,
        executable_path,
        executable_sha256,
        OLLAMA_SID,
        evidence_path,
        evidence_sha256,
        transport,
        listener_owner,
    )
    with pytest.raises(
        DumbMoneyWindowsServiceError,
        match="model digest mismatch",
    ):
        wrong()

    wrong_owner = PinnedOllamaModelVerifier(
        "gpt-oss:20b",
        "3" * 64,
        executable_path,
        executable_sha256,
        OLLAMA_SID,
        evidence_path,
        evidence_sha256,
        transport,
        lambda _host, _port: (
            42,
            executable_path.with_name("not-ollama.exe"),
            OLLAMA_SID,
        ),
    )
    with pytest.raises(
        DumbMoneyWindowsServiceError,
        match="not owned by the pinned identity and executable",
    ):
        wrong_owner()


@pytest.mark.skipif(os.name != "nt", reason="Windows TCP owner API")
def test_windows_tcp_owner_resolves_exact_loopback_listener_process() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = int(listener.getsockname()[1])

        process_id, image_path, process_sid = _windows_loopback_listener_owner(
            "127.0.0.1",
            port,
        )

    assert process_id == os.getpid()
    assert image_path.is_file()
    assert image_path.name.casefold() == "python.exe"
    assert process_sid.startswith("S-1-5-")


@pytest.mark.skipif(os.name != "nt", reason="Windows byte-range process lock")
def test_data_root_lease_blocks_concurrent_writer_and_releases_after_exit(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "service.lock"
    context = multiprocessing.get_context("spawn")

    with _DataRootLease(lock_path):
        blocked_queue = context.Queue()
        blocked = context.Process(
            target=_probe_data_root_lease,
            args=(str(lock_path), blocked_queue),
        )
        blocked.start()
        blocked.join(10)
        assert blocked.exitcode == 0
        assert blocked_queue.get(timeout=2) == "blocked"

    acquired_queue = context.Queue()
    acquired = context.Process(
        target=_probe_data_root_lease,
        args=(str(lock_path), acquired_queue),
    )
    acquired.start()
    acquired.join(10)
    assert acquired.exitcode == 0
    assert acquired_queue.get(timeout=2) == "acquired"
