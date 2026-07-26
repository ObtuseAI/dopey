# DOPEY Meta-Capability Foundry Review

Date: 2026-07-24

Repository: `C:\Users\CH\dopey`

Scope: all repositories visible under `ObtuseAI`, a current GitHub open-source capability survey, and bounded implementation of the highest-value integrity foundations

Decision boundary: paper-market research only; no broker connection, credentials, live orders, automatic foreign-code installation, or readiness credit

## Executive verdict

DOPEY is materially stronger after this pass, but it is not honestly describable as the best trading agent in the world today. The current action gate remains `not_action_ready`: one of 200 required resolved context decisions, four of 100 required closed forward trades, no familywise cohort edge, and no regime-robust cohort proof. The compounding gate remains closed because the measured geometric mean trade return is negative.

The highest-value gap was not another model or strategy library. It was the scientific substrate needed to prevent a powerful autonomous system from fooling itself. This pass therefore implemented:

- collision-safe semantic random streams and a protocol-derived fixed common-random-number seed panel;
- candidate/genome/dataset/era/frame-bound replay manifests, with untrusted local manifests capped at shadow-only;
- content-addressed evaluation specifications and honest proposed-versus-persisted lifecycle counts;
- cognitive evaluation contamination detection and fail-closed local evaluator trust;
- content-hash verification for every canonical memory record;
- a rebuildable causal/provenance memory graph;
- streaming cognitive-ledger duplicate/conflict audits;
- an indexed SQLite projection over the 321,416-record canonical trade-memory ledger;
- a pinned, license-aware, execution-free repository capability foundry;
- capability discovery semantics that distinguish installed or cached presence from observed usable behavior.

Every repository candidate remains quarantined. The foundry grants no runtime, execution, readiness, promotion, or trade authority.

## Organization-wide inventory

The authenticated organization inventory contained exactly seven non-archived, non-fork repositories. DOPEY is the target; the other six were reviewed for reusable architecture and source-license boundaries.

| Repository | Visibility and license | Reviewed commit | Highest-value DOPEY contribution | Reuse decision |
|---|---|---:|---|---|
| `ObtuseAI/blunder` | Private, proprietary | `9489537b6f10e42cdb27eac87cb3a687fc818405` | Typed tool contracts, quarantined capability foundry, observed-use proof, browser and agent evaluation | Clean-room architecture reference only |
| `ObtuseAI/dimwit` | Private, proprietary | `2bf1fa0b342eb119ae90800d37c7f8d73ca110d0` | Calibrated vision quorum, deterministic optical checks, golden-image manifests | Clean-room architecture reference only |
| `ObtuseAI/doofus` | Private, MIT | `c86929343c082c0ce532811877ebe246f8232b22` | Knowledge-boundary scoring, causal confidence, compute allocation, MAP-Elites quality diversity | Direct MIT adaptation candidate with attribution |
| `ObtuseAI/dummy` | Private, proprietary | `e3143e69f0d15d5d5f88738e16a5941434d1733f` | Bitemporal world model, scientific memory, lineage allocation, repository harvesting, governed web intake | Clean-room architecture reference only |
| `ObtuseAI/nimrod` | Private, proprietary | `2c31c24e55f6593867c1a5760629dfbea46ea429` | Evaluator isolation, resource leases, witness checkpoints, tamper-evident journals | Clean-room architecture reference only |
| `ObtuseAI/universal-sports-engine` | Public, MIT | `72853d287099fdcbc0bd6f4f947d9353ce316d82` | Semantic BLAKE2b RNG, deterministic replay, paired simulations, hash-bound evidence | Direct MIT adaptation with attribution |
| `ObtuseAI/dopey` | Private target | `3ee7ec2` observed organization head | Existing research, simulation, memory, risk, and paper-market control plane | Modified locally; no commit created |

Direct source reuse was limited to the MIT semantic RNG pattern from `universal-sports-engine`. Proprietary repositories were used only to identify architectural patterns. No proprietary source was copied into DOPEY.

### Best internal patterns to build next

1. A clean-room bitemporal market world model based on observed time, valid time, revision chains, source families, leases, and explicit stale/missing/contradicted states.
2. A signed evaluator process with an independent principal, read-only inputs, denied egress, separate output ACLs, resource leases, and externally pinned witness checkpoints.
3. A lineage-aware research allocator with reward-hacking canaries and quality-diversity niches based on regime, mechanism, turnover/cost, and failure mode.
4. A calibrated advisory vision layer that uses deterministic geometry/OCR first and multimodal semantic challengers second. Vision must never become quote, price, fill, or readiness truth.
5. A governed page-fetch and claim-extraction broker with immutable source bytes, retrieval time, content hash, citations, redirect/SSRF controls, and source-quality receipts.

## Current external capability survey

The governed catalog contains 26 external repositories pinned to exact observed commits. Repository activity, stars, and human architecture-fit scores are discovery signals only; they are not evidence of correctness, edge, or safe integration.

| Capability cell | Candidates reviewed | Recommended DOPEY use |
|---|---|---|
| Point-in-time truth and lineage | [Feast](https://github.com/feast-dev/feast), [OpenLineage](https://github.com/OpenLineage/OpenLineage), [MLflow](https://github.com/mlflow/mlflow), [Great Expectations](https://github.com/great-expectations/great_expectations) | Offline point-in-time joins; small native lineage events; optional local trace mirror; dataset-contract ideas |
| Independent evaluation | [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai), [BrowserGym](https://github.com/ServiceNow/BrowserGym), [AgentRx](https://github.com/microsoft/AgentRx), [Microsoft Skills](https://github.com/microsoft/skills) | Deterministic task packs, browser competence tests, trajectory failure localization, selective skill routing with observed-use ledgers |
| Uncertainty and falsification | [MAPIE](https://github.com/scikit-learn-contrib/MAPIE), [DoWhy](https://github.com/py-why/dowhy), [ruptures](https://github.com/deepcharles/ruptures), [sktime](https://github.com/sktime/sktime) | Blocked/time-aware conformal intervals, causal refuters, negative controls, causal changepoint/regime adapters |
| Differential simulation | [QuantLib](https://github.com/lballabio/QuantLib), [LEAN](https://github.com/QuantConnect/Lean), [NautilusTrader](https://github.com/nautechsystems/nautilus_trader), [QuantReplay](https://github.com/Quod-Financial/quantreplay), [hftbacktest](https://github.com/nkaz001/hftbacktest) | Feed identical frozen scenarios through independent paper-only oracles; preserve disagreements as triage evidence |
| Automated research | [Qlib](https://github.com/microsoft/qlib), [RD-Agent](https://github.com/microsoft/RD-Agent), [Optuna](https://github.com/optuna/optuna) | Point-in-time research records; proposer/developer/experiment/falsifier loop; constrained nested optimization with experiment-family accounting |
| Governed web and document intelligence | [Playwright](https://github.com/microsoft/playwright), [Crawl4AI](https://github.com/unclecode/crawl4ai), [Docling](https://github.com/docling-project/docling) | Read-only allowlisted acquisition; source-hashed page snapshots; local document/OCR/chart-table challengers |
| Temporal evidence memory | [Graphiti](https://github.com/getzep/graphiti) | Derived bitemporal evidence-graph patterns; canonical append-only artifacts remain truth |
| Default-deny sandboxes | [OpenShell](https://github.com/NVIDIA/OpenShell), [OpenSandbox](https://github.com/alibaba/OpenSandbox) | Threat-model and escape/egress bakeoff behind a DOPEY-owned sandbox protocol |

The catalog also reviewed all pinned source and license metadata in:

- `dopey_acceleration/capability_sources.json`
- `artifacts/dopey/acceleration/capability_foundry/latest_snapshot.json`

The strongest design is not a monolithic imported trading stack. It is a differential research mesh:

```text
immutable point-in-time input
  -> DOPEY canonical evaluator
  -> independent pricing/execution oracles
  -> disagreement artifact
  -> falsification and uncertainty layer
  -> signed evaluator
  -> forward-only promotion ledger
```

### Explicit non-adoptions

- FinRL, FinGPT, or any other repository as a drop-in trading brain.
- Live or broker adapters present in LEAN, NautilusTrader, hftbacktest, Qlib, or adjacent packages.
- Synthetic markets, vision output, scraped prose, or researcher-agent prose as forward evidence.
- ABIDES as a dependency; its architecture remains useful, but the repository is comparatively stale.
- Unrestricted self-editing, self-grading, or mutation of evaluators, readiness gates, safety policy, or trade authority.
- Bulk skill or MCP registries.
- Cloud sandboxes that require new accounts or credentials before a local bakeoff establishes need.
- Graph/vector state as canonical memory.

## Implemented integrity foundations

### 1. Bound simulation evidence and common random numbers

`dopey/simulation/semantic_rng.py` adapts the MIT semantic RNG pattern from `ObtuseAI/universal-sports-engine@72853d2`. Labels are now type-tagged and canonically encoded, so integer/string and embedded-delimiter collisions cannot alias random streams.

Every challenger in a cycle must share the same dataset, sealed-era set, observation-generator version, and candidate-invariant sampling-frame hash. Sampling-frame bindings preserve typed field presence, so missing and explicit null values cannot alias when cohort semantics differ.

The evaluator derives a fixed three-seed panel only from content identities and protocol versions. Candidate labels, candidate-set membership, dataset labels, generator labels, calibration fields, and tunable statistical parameters cannot steer the panel. Every challenger faces every common-random-number seed, and comparison uses the worst fitness result with an immutable fixed-panel-index tiebreaker. A caller-supplied seed must match the content precommitment before any replay executes.

Replay observations are bound to candidate ID, challenger genome ID, dataset hash, era hash, stable row frame, generator version, and complete observation content. Replay artifacts also carry canonical causal input records and their hash. Validation recanonicalizes those inputs, enforces exact nested schemas and invariants, independently reruns the causal evaluator with the bound seed and parameters, and requires exact output equality. Swapped, stale, frame-drifted, structurally colliding, or self-consistently forged manifests and causal results fail.

The local manifest builder is intentionally marked untrusted. It cannot self-assert a signature, key, independent evaluator, or verified dataset snapshot, and every result it produces is capped at `SHADOW_ONLY`. A future signed evaluator trust root is required before `HELD_OUT_VALIDATED` can be recommended.

The root commitment, complete fixed seed panel, randomization policy, evaluation parameters, evaluator version, and immutable input identities form a content-addressed evaluation specification. Replay, candidate evaluation, and cycle artifacts bind that specification. Candidate identities are recorded in a separate attempt commitment and cannot influence seed selection. The local runtime explicitly records that no external signed seed commitment or authorized append-before-return attempt ledger exists yet. Evaluation archives key attempts by `evaluation_id`, so materially different evaluation specifications for one candidate are retained rather than overwritten.

Promotion, rollback, and retirement artifacts now say `proposed_not_persisted` or `recommended_not_persisted`. The cycle reports zero automatic or persisted transitions unless a future persistence layer actually applies one.

### 2. Fail-closed cognitive evaluator trust

The cognitive task loader now:

- hashes candidate feature vectors and the expected feature vector while excluding every renameable task, partition, domain, family, provenance, and candidate label;
- rejects exact semantic reuse across visible/private/external/forward partitions;
- rejects task-store path escapes, malformed JSON, invalid candidates, duplicate identities, and partition mismatches;
- records a task-store audit;
- separates its semantic contamination hash from a full-content/provenance hash;
- treats every local raw task store as unsigned and OS-unverified;
- permits zero activation from that local store.

Visible trials cannot dilute hidden failures. Promotion metrics use the worst result across private, external-generalization, and real-forward partitions, and every hidden partition must be trusted. Discovery cycles require an exact schema and a valid canonical cycle hash; the source-cycle and task-store content hashes bind trials, evidence, and ledger identities.

Both cognitive ledgers are preflighted before derived artifacts publish, and `latest_evidence_cycle.json` advances last. Visible-only evaluation and unsigned local task stores remain quarantined. A real activation requires a future signed, isolated evaluator trust root; no local JSONL shape can assert independence.

Future cognitive ledger writes are idempotent. Existing historical duplicates were audited but not rewritten or deleted.

### 3. Verifiable canonical memory and derived graph

Every memory ledger load now enforces the exact 14-field v1 envelope, required artifact/version literals, sorted lineage, payload shape, and all four research-only safety booleans before recomputing the canonical content hash and verifying that identity is bound to kind and content. Tampered, internally rehashed unsafe, incomplete, extended, or spoofed records raise explicit errors.

The new memory graph is a rebuildable projection over validated ledgers. It records causal-parent and source-provenance edges, detects causal cycles and parent-after-child temporal violations, and represents unresolved external references explicitly.

Current snapshot:

- status: `complete_derived_index`
- memory nodes: 62
- external reference nodes: 149
- edges: 650
- causal cycles: 0
- temporal-order violations: 0
- graph hash: `eb5fe8a04ef938310ec440b565a36bf80e6fa7c425f996608d66dc4db11de3c1`

### 4. Indexed trade-memory projection

The 115 MB canonical trade-memory JSONL remains the source of truth. A rebuildable SQLite projection now provides indexed family, condition, symbol/date, and content-hash retrieval without loading the complete JSONL into memory.

The builder rejects lexical, resolved, symlink, and hard-link aliases between canonical JSONL and SQLite. JSONL, SQLite, manifest, and summary are built under one locked generation, validated for SQLite integrity and line-by-line parity, and only then published. Stable files are byte-exactly rolled back if any publication or post-publication validation fails.

Current manifest:

- generation: `20260724T074816531920Z-de428536712a`
- packet validation: passed
- indexed JSONL/SQLite parity: true
- rows: 321,416
- unique canonical content hashes: 321,416
- duplicate canonical content rows: 0
- source JSONL SHA-256: `db882f8732a05983cccccaf6315746adfdc4b2efd2e2b6fcc1683776c9da8051`
- SQLite SHA-256: `d8c7686b258118eca95d104d51321ebe3779eef8b5f065a0e154a4ae154bd850`
- manifest hash: `6c445523f87afbb641201d50783cf29a22f72f092bd6adb29ff4f9482c12c9e1`

The index preserves semantically identical rows as distinct events by binding identity to source line plus canonical content hash.

### 5. Cognitive-ledger integrity audit

The existing cognitive trial ledger contains:

- rows: 26,880
- unique trial IDs: 19,824
- identical duplicate rows: 7,056
- conflicting trial IDs: 0

The evidence-cycle ledger contains 35 rows, 35 unique identities, and zero conflicts. Historical rows were preserved. Future identical appends are skipped; conflicting identity/content pairs raise.

### 6. Governed repository capability foundry

The foundry validates exact local source schemas, repository/URL binding, 40-character Git commit syntax, timestamp shape, license assertions, scores, and capability IDs. It does not claim that its offline process remotely reverified commit/ref identity, license blobs, or capability evidence paths. That provenance gate is explicitly false for every candidate.

The consumer verifies the foundry reproducibility hash and exact artifact type, schema, producer version, status, catalog version, and catalog hash. Self-consistent stale artifacts are reported as incompatible rather than consumed.

The foundry emits:

- 32 pinned candidates;
- six internal architecture sources;
- 26 external open-source sources;
- ranked capability slices;
- a content-addressed repository-to-capability graph;
- adoption modes based on license boundaries;
- an explicit `not_observed_usable` runtime status for every candidate.

Foundry snapshot:

- foundry version: `dopey-capability-foundry-v2`
- catalog version: `dopey-capability-source-catalog-v2`
- capability discovery version: `dopey-agent-capability-discovery-v7`
- status: `complete_quarantined_unverified_provenance_candidates`
- observed at: `2026-07-24T06:50:00Z`
- catalog hash: `f87fddc3529b3f2c155ac5b1cd8836699064c117bb209d104fa83f0f365a1cd2`
- reproducibility hash: `2f3aac7c50b82adaf7000ab6933ccd8df0fa21b9db4238d2ac729da5ed5fca23`
- remote provenance verification: `not_performed_by_offline_foundry`
- foreign source downloaded: false
- foreign code executed: false
- package installed: false
- automatic installation/copy/activation: false
- runtime capabilities proven: 0
- readiness/execution/trade-authority effect: none

## Verification

Focused integration proof:

```text
118 passed in 17.61s
Ruff lint: passed
Ruff format check: passed
Scoped git diff whitespace check: passed
```

The test set covers capability foundry quarantine and full-content recomposition, capability discovery semantics, cognitive evaluator trust and contamination, cognitive-ledger audits, memory integrity and graph behavior, typed sampling-frame identity, independently recomputed causal replay, deterministic fixed-panel seed commitments, order-invariant evolution replay, indexed trade-memory parity, acceleration control-plane boundaries, and hardening invariants. A final adversarial re-audit found no remaining P0/P1 issue in the touched capability-foundry and recursive-evolution scope after the replay and seed fixes.

The repository remains intentionally uncommitted for review. Unrelated scheduler-generated data/report changes already present in the dirty worktree were not reverted or rewritten.

## Highest-value next build order

### P0: signed evaluator trust root

Run private/external/forward cognitive tasks under a distinct process or principal with read-only immutable inputs, denied network, bounded resources, separate outputs, signed partition manifests, pinned evaluator identity/version/key, externally committed seed panels, append-before-result attempt receipts, and externally pinned witnesses. Until that exists, activation must remain zero.

### P1: point-in-time truth kernel

Implement a small DOPEY-native bitemporal dataset contract and offline point-in-time join adapter, informed by Feast and OpenLineage. Required fields are event time, observed time, revision identity, source family, availability lag, transformation hash, and explicit missing/stale/contradicted status.

### P1: differential oracle mesh

Start with QuantLib for frozen derivatives fixtures. Then compare paper-only event scenarios with LEAN and one isolated microstructure engine. Never average disagreement away; emit a triage artifact that identifies calendar, fee, fill, price, Greek, and state-transition differences.

### P1: measured agent and skill competence

Create Inspect AI and BrowserGym packs for source attribution, prompt-injection refusal, blocker preservation, tool selection, timeout honesty, filing/table retrieval, and unsafe-action refusal. A skill becomes usable only after task-level observed success under explicit budgets.

### P1: remote source-provenance gate

Add an authenticated, immutable GitHub metadata snapshot with repository/ref identity, license-blob hashes, capability evidence paths, API response hashes, and snapshot signatures. Only candidates that pass that gate may advance from discovery quarantine to a bounded integration replay.

### P2: governed source and document intelligence

Build allowlisted Playwright acquisition, immutable response/screenshot hashes, deterministic Docling extraction, source-span claims, contradiction search, and a derived temporal evidence graph. All content is untrusted input; no web text or vision result earns edge/readiness credit.

### P2: sandbox bakeoff

Evaluate OpenShell and OpenSandbox through one DOPEY-owned interface. Mandatory gates are default-deny network/filesystem, immutable inputs, disposable outputs, CPU/RAM/time/process limits, deterministic environments, full command/network/artifact ledgers, and absolute denial of broker, credential, readiness-policy, and safety-policy surfaces.

### P2: bounded recursive research cell

Use a typed factor/hypothesis DSL and an immutable proposer -> developer -> experiment -> falsifier -> promotion protocol. Candidate code runs only in the winning sandbox. It cannot read private answers, modify evaluators, expand permissions, install arbitrary dependencies, or count synthetic results as forward evidence.

## Bottom line

This pass closes meaningful meta-agent integrity gaps and turns the repository survey into a durable, executable capability intake surface. It does not manufacture edge or readiness. DOPEY's path to exceptional performance is now clearer:

1. make truth point-in-time and lineage-complete;
2. make evaluation externally trustworthy;
3. make simulation disagreements measurable;
4. make uncertainty and falsification first-class;
5. make every tool and skill prove observed competence;
6. let recursive improvement operate only inside those fixed boundaries;
7. demand real forward evidence before any action claim.

That is the shortest honest route toward a genuinely elite research agent.
