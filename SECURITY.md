# Security Policy

DOPEY is public, experimental financial-research software. Security boundaries
cover the source code, release pipeline, local data handling, append-only
evidence, operator controls, and the separately gated broker-capable package.

## Supported Versions

| Version | Supported |
| --- | --- |
| Current `public-release` branch | Yes |
| Older commits and forks | No |

## Reporting a Vulnerability

Do not open a public issue, discussion, or pull request for a suspected
vulnerability.

Report vulnerabilities privately through GitHub's **Report a vulnerability**
flow on the Security tab when available. If that channel is unavailable, email
**cjharriskc@gmail.com**.

Include:

- the affected component and commit;
- reproducible steps or a minimal proof of concept;
- expected and observed behavior;
- likely impact, including any data, credential, ledger, or order-authority
  boundary crossed;
- suggested remediation, if known.

Do not include real credentials, broker account data, private market datasets,
or personal information in the report. Use redacted samples.

## Security and data boundary

- The public repository intentionally contains no secrets, broker sessions,
  account history, private runtime evidence, or provider market datasets.
- `.env`, private key, local MCP, local agent configuration, and governed market
  lake paths are ignored.
- New research logic is paper-only and live-blocked until independent evidence
  and explicit operator gates authorize otherwise.
- `dopey_live/` is the only broker-capable package. A research result alone
  never grants order authority.
- Missing provenance, authentication, reconciliation, or ledger integrity fails
  closed.

See [`DATA_NOTICE.md`](DATA_NOTICE.md) for the public data policy.

## Response process

The maintainer will validate the report, determine affected versions, prepare a
fix, and coordinate disclosure. Confirmed vulnerabilities may be published as a
GitHub security advisory after a remediated release is available.
