# DumbMoney Robinhood venue cell

`dopey_live` is the sovereign Robinhood execution cell for DumbMoney. The
older `dopey_execution` Robinhood adapter remains a discovery-only denial stub
and is not imported or routed by this integration. DumbMoney Core can narrow
DOPEY authority; it cannot enlarge the owner control, broker account scope,
settled cash, local risk policy, research gates, or broker capabilities.

## Release status

The private-local Windows service entrypoint is
`dopey_live.dumbmoney_windows_service:main`, packaged as
`DumbMoneyDopeyRobinhood.exe`. It is separate from the inherited operator CLI;
that CLI cannot satisfy the service credential, discovery, or freshness
contract and remains fail-closed in strict mode.

Importing any DumbMoney module starts no listener, timer, thread, network
request, or broker call. Service startup validates configuration and
credentials, acquires its ProgramData lease, starts a loopback-only health
endpoint, and writes a signed `RECONCILIATION_ONLY` readiness descriptor. It
waits one poll interval before its first read-only reconciliation. New exposure
can be considered only on a later cycle.

The legacy standalone operator remains available outside strict release mode.
A manually supplied signed capital envelope can be used for preflight:

```powershell
py -3.12 -m operator_tools.operator_live_branch `
  --dumbmoney-envelope C:\secure\capital-envelope.json `
  --dumbmoney-public-key C:\secure\dumbmoney-core.pub `
  --dumbmoney-account-hash <lowercase-sha256>
```

The legacy CLI is read-only preflight: every `--execute` invocation is rejected
before gateway or model construction, including programmatic calls through its
crash-tombstone wrapper. Production execution exists only in the supervised
Windows service. A static envelope is not the production Core command channel.
The manually supplied envelope file must be exact canonical UTF-8 JSON:
duplicate keys, non-finite numbers, floats, alternate key order/whitespace, a
byte-order mark, and trailing bytes are rejected.

## Authenticated pull-only command feed

Core exposes the local-only endpoint:

```text
GET http://127.0.0.1:<port>/v1/cells/dopey_robinhood/commands
    ?after=<global_sequence>&cursor=<event_digest>&limit=<bounded_limit>
    &request_nonce=<64-lowercase-hex>
```

Use `DumbMoneyCommandFeedClient` to bind deployment-owned dependencies. The
bearer provider must read the per-cell secret from an OS-backed secret store;
the bearer is never accepted from a CLI flag, environment variable, persisted
state, log, or artifact. The HTTP transport is also injected, so library import
cannot contact Core.

```python
from datetime import datetime
from pathlib import Path

from dopey_live import (
    DumbMoneyCommandFeedClient,
    DumbMoneyContractResolverClient,
)
from dopey_live.dumbmoney_command_feed import command_feed_state_path
from operator_tools.operator_live_branch import run_supervised_dumbmoney_cycle

repository_root = Path(r"C:\path\to\dopey")
client = DumbMoneyCommandFeedClient(
    base_url="http://127.0.0.1:8765",
    cell_bearer_provider=os_secret_provider,
    trusted_public_key=trusted_core_public_key,
    trusted_operator_public_keys=sealed_operator_public_key_map,
    expected_account_hash=pinned_agentic_account_hash,
    state_path=command_feed_state_path(repository_root),
    transport=loopback_http_transport,
)
resolver = DumbMoneyContractResolverClient(
    base_url="http://127.0.0.1:8765",
    cell_bearer_provider=os_secret_provider,
    trusted_core_public_key=trusted_core_public_key,
    trusted_promoter_public_keys=sealed_promoter_public_key_map,
    trusted_research_public_keys=sealed_research_public_key_map,
    trusted_evaluator_public_keys=sealed_evaluator_public_key_map,
    transport=loopback_http_transport,
)

# The helper polls under the Live Branch process lock, then passes the same
# callable to the broker-sink guard for immediate pre-spawn and post-return polls.
result = run_supervised_dumbmoney_cycle(
    client.poll_once,
    resolver,
    execute_orders=False,
)
```

`os_secret_provider`, the Core/operator/promoter/research/evaluator public
keys, the account hash, and `loopback_http_transport` are deployment
dependencies, not repository defaults. The production Windows runner supplies
these bindings from one exact-SHA public config and two Credential Manager
targets.

The consumer:

- restricts Core to an exact `http://127.0.0.1:<port>` origin;
- sends the injected bearer only in the request authorization header;
- generates a fresh cryptographically random 32-byte request nonce for every
  poll and rejects any top-level or signed-checkpoint echo mismatch;
- verifies the page checkpoint with the pinned Core key;
- recomputes every full ledger-event proof and binds its event identity,
  source sequence, signer, body digest, timestamps, causality, and hash-chain
  material to the original signed envelope;
- accepts capital envelopes only from the Core key and kill/desired-mode
  envelopes only from the disjoint sealed operator key set;
- enforces per-control monotonic generation/revision continuity;
- advances a digest cursor and atomically replaces its local state file;
- re-verifies persisted commands after restart;
- replays expired signed history to recover sequence state, while never
  granting stale/future LIVE mode or capital;
- preserves an expired active kill as active until a newer signed generation
  clears it;
- maps authentication, transport, state, schema, signature, gap, cursor,
  pagination, omission, and unknown failures to `kill_active=True` or
  paused/unknown, never to positive authority.

The Core-signed checkpoint covers the request cursor, ordered command
projections and complete ledger proofs, next cursor, ledger head, observation
time, required action, and per-request nonce. Page fields must exactly match
that checkpoint. This prevents an untrusted transport from replaying, omitting,
or rewriting a command. Core and its signing key remain the root control-plane
trust boundary, so keep them inside the protected host and prove kill latency
during the attended canary.

## Core-backed local rollback anchors

Before any broker reconciliation and again after command-state and cycle
mutations, the Windows runner publishes integrity-checked heads for the command
cursor, live-branch ledger, and paper-twin ledger to Core's authenticated
`/v1/cells/dopey_robinhood/journal-heads:anchor` route. Each request binds the
pinned account, deterministic journal stream, local sequence, local head, and
fresh nonce. Dopey accepts the result only after verifying the Core-signed
anchor envelope, request-bound checkpoint, and recomputed global-ledger proof.

Core rejects a lower sequence or a different head at the same sequence. Dopey
therefore detects restored, truncated, or forked local state even if the local
files remain internally hash-consistent. A rejected pre-cycle anchor returns
`blocked_rollback_anchor` before any Robinhood contact. A failed post-cycle
anchor makes readiness `BLOCKED`, disables the following execution cycle, and
preserves the cycle result for reconciliation. `/health/ready` requires current
anchors, complete reconciliation, and `execution_enabled=true`; mere process
liveness or read-only reconciliation is not execution readiness.

## Capital and promotion authority

`CapitalEnvelopeV1` is Ed25519-signed, account-bound, and valid for at most 60
seconds. The cell verifies it at cycle allocation, at broker-sink preparation,
and again through the refreshed command feed immediately before the external
write boundary.

The contract requires:

- exactly one `strategy_hash`, one `passport_hash`, and one `promotion_hash`,
  forming a single non-mixable tuple per capital lease;
- sorted, nonempty, exact Robinhood sink identities:
  `equity:<UPPER_SYMBOL>` or
  `option:<UPPER_SYMBOL>:<exact_contract_id>`;
- `max_order_risk_cents <= max_correlated_risk_cents <=
  max_open_risk_cents`;
- positive open-order, daily-loss, generation, and policy-epoch limits.

Wildcards, symbol prefixes, instrument-class-only grants, source-hash aliases,
and multi-candidate capital sets are rejected. Local signal builders leave
`passport_hash` and `promotion_hash` empty. The resolver derives both values;
caller-supplied values are rejected.

For each buy, Dopey calls the authenticated Core route:

```text
GET /v1/cells/dopey_robinhood/contracts/<body_digest>
    ?request_nonce=<64-lowercase-hex>
    &capital_envelope_digest=<active-capital-body-sha256>
```

It verifies the nonce-bound Core checkpoint, complete recomputed ledger proof,
active capital digest and fencing generation, original signed envelope, and
currentness projection. Promotion certificates must come from the disjoint
sealed promoter key set; passports must come from the disjoint sealed research
key set. Each resolution must also contain the Core-signed
`dumbmoney.cell-authority-state.v1` projection for the same ledger state. Dopey
requires current LIVE mode, clear kill state, the exact mandate, policy epoch,
capital fence, strategy/passport/promotion tuple, at least two unique current
PASS verdict facts from distinct courts and sealed evaluator signer IDs, and a
ledger head continuous with the requested contract proof. The promotion and
passport reads must resolve against one identical authority state. Venue,
exact instrument, policy epoch, strategy, passport link, and maximum loss must
agree with the active singleton capital tuple. The full resolution occurs at
preflight, broker-sink preparation, and inside each final broker-boundary
guard. A changed event, signer, lineage, verdict, ledger head, capital fence,
or expiry fails closed.

The canonical cross-repository positive fixture is
`tests/fixtures/dumbmoney/signed-capital-envelope.v1.json`, whose file SHA-256
is
`b0fe2fa0261b2dc36e4043e8c33b91b1016676e04a25e4b4d5bd66eea0c9079a`.
Local negative conformance cases cover both invalid cap-order directions.

A persisted fence binds the complete authority identity:

```text
(envelope_id, event_id, body_digest, fencing_generation, policy_epoch)
```

Reusing one generation with any different identity is rejected, and a stale
generation cannot regain authority after process-lock reacquisition.

## Deterministic broker-write checkpoint and revocation window

The generative subprocess receives neither the Robinhood bearer nor the
Robinhood MCP endpoint. Broker reads and writes occur only in the parent
process through `DeterministicRobinhoodMcpClient`; a configured parent
transport cannot fall back to a model-selected tool call.

[Robinhood's official Agentic overview](https://robinhood.com/us/en/support/articles/agentic-trading-overview/)
says an authenticated agent may read all Robinhood accounts but can place
trades only in its Agentic account. Dopey therefore calls `get_accounts` inside
every write session, requires exactly one explicitly labeled Agentic account,
and binds its SHA-256 to the account hash sealed in both runner config and
capital authority. The current equity write schemas expose no account
selector; adding one is schema drift and blocks the call. This same-session
proof plus Robinhood's server-side Agentic-only write contract prevents silent
default-account selection.

The phase-one write path is deliberately equity-only:

1. persist `DISPATCHING` with zero placement retries;
2. refresh kill, mode, capital, exact authority identity, fence, promotion,
   passport, local kill, and current account evidence;
3. require more than the configured 30-second write timeout plus a 5-second
   safety margin on the authority lease;
4. construct one exact quantity-mode equity argument object locally;
5. open a one-shot official Streamable HTTP MCP session, verify the live
   `review_equity_order` and `get_accounts` schemas, prove the pinned Agentic
   account, and call review exactly once;
6. bind the typed review response to the exact local arguments and require
   explicit approval;
7. refresh the complete signed authority again after review and immediately
   before placement;
8. open a second one-shot MCP session, verify the live place/account schemas,
   prove the same pinned Agentic account, refresh authority after schema
   verification, and call `place_equity_order` exactly once with the identical
   argument object;
9. never retry an attempted placement; an incomplete, conflicting, timed-out,
   or non-attested response is ambiguous and enters reconcile/cancel;
10. refresh controls again after return.

The direct client disables proxy inheritance and redirects, pins the MCP
protocol version, checks request IDs and typed JSON/SSE responses, closes
initialized sessions in a `finally` path, rejects tool schema drift before the
write call, and exposes only sealed read tools plus the three equity
review/place/cancel names to parent code. Parent reads preserve broker evidence
without model normalization: negative/overflow balances, missing or
conflicting position economics, incomplete history, bad timestamps, and
missing/extra quote symbols fail closed. Option writes remain blocked until
their exact current schemas, contract identity, quotes, and result semantics
receive the same deterministic adapter.

A kill that arrives after step 7 can still race the single outbound placement
request. The system does not claim instantaneous revocation. The bounded
timeout, at-most-once dispatch, ambiguous state, post-return poll, and
immediate cancel/reconcile remain the truthful in-flight guarantees.

## Risk and sell-side behavior

New exposure intersects the signed grant with settled cash, complete broker
positions, all active orders, worst-case intent loss, and witnessed daily loss.
Worst-case buy risk must fit the remaining daily-loss capacity; equality at
the boundary is allowed. Missing broker fee evidence or missing unrealized PnL
blocks the calculation rather than being represented as zero.

Until a signed cross-account risk snapshot carries independently witnessed
cluster attribution, DOPEY conservatively applies the correlated-risk ceiling
to total observed open risk. It does not claim a reconciliation receipt digest,
high-water drawdown, or true cluster-level attribution it cannot witness.

Sells are risk-reducing only. A sell requires exactly one fresh matching long
broker position, a positive finite quantity no greater than the witnessed
holding, and no active sell for the same stock or exact option contract. Naked
sells, oversells, and duplicate exits fail closed.

## Kill and degraded operation

Either a signed feed kill or the local file
`artifacts/dopey/live_branch/DUMBMONEY_KILL.v1` blocks new exposure. An active
kill:

1. attempts one deterministic official-MCP cancellation for each active,
   DOPEY-attributed equity order;
2. polls complete order history at most three times;
3. reports `CANCEL_ONLY_DEGRADED` until history is terminal and reconciled.

Production cancellation uses only the sealed `cancel_equity_order` parent-side
adapter. Option cancellation remains blocked until it receives the same
deterministic schema and result attestation. The cancel path never reviews,
replaces, or places an order. Unattributed orders, unidentified ambiguous
submissions, option orders, and residual positions remain attended blockers;
they are not silently represented as canceled or flat.

Ambiguous placement is never retried. The cell resolves it automatically only
when bounded, complete read-only broker history supplies one exact match for
account, instrument, contract, side, quantity/notional, limit, time-in-force,
market date, and the submission window. Every other case remains
operator-visible and cancel-only.

## Laptop migration and attended canary

Move non-secret DOPEY data from the laptop as a content-hashed, staged import
under `C:\ProgramData\DumbMoney\dopey-robinhood`; do not copy OAuth cookies,
browser profiles, bearer tokens, or plaintext credentials.

## Private-local Windows runner

The runner loads only:

- the exact raw bytes of
  `C:\ProgramData\DumbMoney\config\dopey-robinhood-runner.v1.json`, whose
  lowercase SHA-256 must equal `--config-sha256`;
- the cell bearer from Windows Credential Manager target
  `DumbMoney/DopeyCellToken`;
- the official Robinhood MCP bearer profile from Windows Credential Manager
  target `DumbMoney/RobinhoodProfile`.

There is no environment-variable, plaintext-file, hosted coordinator,
telemetry, or public-repository secret fallback.
Core/operator/promoter/research/evaluator public keys, the account hash, Core
readiness pins, release identity, and fixed ProgramData paths are public
config. `role_public_keys_sha256` is the canonical SHA-256 of Core's complete
`role_public_keys_base64url` object. The release must derive the Dopey
readiness signer from the cell credential and require its public-key ID to
equal the sole `dopey_venue` role key; an ambiguous role set fails release
assembly. The absolute Codex child executable and its SHA-256 are also pinned
there; the runner re-hashes it at construction and immediately before every
child spawn, so the credential-bearing process is never selected through
`PATH`. The sealed release installs that dependency at
`C:\Program Files\DumbMoney\releases\<release-id>\tools\codex\codex.exe`;
the runner does not download or fabricate it.

Any local generative Codex execution is forced to `--oss --local-provider
ollama` at the literal `http://127.0.0.1:11434/v1` endpoint, without Robinhood
MCP configuration or broker credentials. It never inherits `HOME`,
`USERPROFILE`, `CODEX_HOME`, `OPENAI_API_KEY`, or a hosted-provider credential.
The public config pins one explicit, non-`latest`, non-`cloud` Ollama model tag
and its 64-character manifest digest, plus the absolute Ollama server
executable and its SHA-256. Immediately before every Codex spawn,
the runner uses the Windows TCP owner table to require exactly one
`127.0.0.1:11434` listener, resolves its process image, requires the pinned
absolute path and binary hash, reads the loopback-only `/api/tags` inventory,
requires exactly one matching tag/model/digest tuple, then re-checks that the
same PID, process SID, image, and hash still own the listener. Missing,
ambiguous, changed, wildcard-bound, wrong-owner, or path-hijacked local model
state blocks the broker operation before the subprocess.

The config also pins the raw SHA-256 of the static installation attestation at
`C:\ProgramData\DumbMoney\dopey-robinhood\evidence\ollama-runtime-evidence.v1.json`.
The release artifact binds the dedicated non-service local process identity,
loopback-only/no-egress policy, executable, ACL-protected model-store owner and
SDDL digest, model-store manifest, and model tag/digest. Dopey hashes that
artifact at use time and then independently revalidates the live listener PID,
owner image, executable hash, and model inventory; the static artifact contains
no restart-volatile PID.
OpenRouter is therefore outside this privileged execution transport; it may be
budgeted for research and planning without becoming Robinhood order authority.

The config schema and release template are
`configs/dumbmoney/schemas/dopey-robinhood-runner.v1.schema.json` and
`configs/dumbmoney/dopey-robinhood-runner.v1.template.json`.

Core discovery reads only the current Core-signed descriptor at
`C:\ProgramData\DumbMoney\readiness\DumbMoneyCore.json`. Dopey verifies its
Core signature, release and artifact pins, short lifetime, broker-none
authority, and literal loopback endpoint before calling `/health/live`,
`/v1/cells/dopey_robinhood/commands`, or the contract resolver. It never
receives the operator token and does not treat the unsigned Core health route
as authority; the nonce-bound Core command checkpoint is required.

The service writes a short-lived Ed25519-signed descriptor to
`C:\ProgramData\DumbMoney\readiness\DumbMoneyDopeyRobinhood.json`. Its signing
key is domain-separated from the Credential Manager cell bearer, and the
derived public-key SHA-256 is pinned in the public config. Readiness reports
`execution_enabled=false` and mode `RECONCILIATION_ONLY` until a complete
broker reconciliation, all current signed controls, and all three Core-backed
local journal anchors agree.

One Windows byte-range lease on the exact ProgramData root excludes concurrent
service writers; the OS releases it on process death, and a restart must
reacquire it before any cycle. Intent reservation and fence activation are
read-check-append transactions under the cross-process ledger lock and are
flushed to disk. An interrupted reservation stays unresolved and blocks a new
dispatch until broker reconciliation. The final guard re-reads the current
fence under that lock, polls fresh Core authority, checks the local kill file,
and runs both before review and again immediately before the one placement
call. Cross-process regression tests prove a second writer is denied while the
lease is held and can acquire only after the first process exits.

The runner gives the Robinhood profile only to the deterministic parent-side
MCP client. No generative process receives the bearer, the MCP endpoint, an
account identifier, or a broker tool. The bearer is never placed in argv,
prompt, ledger, readiness, logs, artifacts, or subprocess environment.
Parent-side MCP evidence remains in memory and only typed redacted snapshots
enter Dopey's ledger.

Before the first live canary:

- install the exact-SHA public config with disjoint Core/operator/promoter/
  research/evaluator public-key roles, the exact canonical Core role-bundle
  digest, the sole matching Dopey venue readiness key, and the dedicated
  Agentic account hash;
- provision the per-cell bearer in the OS secret provider and test 401/403,
  timeout, restart, stale-state, journal rollback/fork, cursor-gap, kill, and
  kill-clear behavior;
- provision the Robinhood profile only in Windows Credential Manager and
  verify it is not inherited from environment or plaintext files;
- install the sealed `DumbMoneyDopeyRobinhood.exe` service runner with the
  exact config SHA argument;
- install the release-selected tool-capable Ollama model locally, populate its
  explicit tag, `/api/tags` digest, absolute server executable, and executable
  SHA-256 in the public config, and deny Ollama cloud models and non-loopback
  listeners;
- prove broker history exposes explicit per-fill fees, or add an attested
  realized-PnL source; missing fee evidence blocks new exposure after a fill;
- add transcript-attested `get_option_quotes` evidence before enabling options;
- perform attended place, cancel, history-convergence, restart, pre-spawn kill,
  and in-flight kill drills at minimum capital;
- keep external confirmation that no unattributed or ambiguous order remains.

These are activation requirements, not profitability or broker-readiness
claims.
