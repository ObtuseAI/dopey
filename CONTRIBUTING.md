# Contributing to DOPEY

DOPEY accepts focused contributions that preserve its evidence-first,
fail-closed architecture.

## Before opening a pull request

1. Search for existing logic before adding a new implementation.
2. Keep research and simulated execution separate from `dopey_live/`.
3. Preserve typed blocked, failed, rejected, queued, and inconclusive states.
4. Add the smallest integration, end-to-end, or smoke coverage needed to prove
   the behavior.
5. Run the repository validation commands from `README.md`.

## Code expectations

- Use Python 3.11 or newer and strict, explicit types.
- Prefer pure, single-purpose functions and immutable inputs.
- Use classes only at external-system connector or interface boundaries.
- Raise specific, actionable errors; do not hide failures with broad exception
  handling or silent fallbacks.
- Keep imports at the top of each module and comments in English.
- Match existing naming, formatting, and deterministic serialization rules.

## Evidence and authority rules

Contributions must not:

- fabricate, relabel, or silently substitute market evidence;
- promote a model from replay or synthetic results alone;
- collapse paper, replay, model-priced, broker-read, or live evidence classes;
- weaken supervisor, risk, settlement, provenance, freshness, or operator gates;
- create broker/order authority outside `dopey_live/`;
- store credentials, tokens, account identifiers, broker history, or private
  runtime evidence;
- add provider market data or locally generated market-lake files.

Read [`DATA_NOTICE.md`](DATA_NOTICE.md) before contributing any fixture. Test
fixtures must be synthetic, deterministic, minimal, and clearly labeled.

## Pull requests

Explain the problem, the evidence for the change, the authority boundary
affected, and the validation performed. Keep unrelated cleanup out of the
patch. Security vulnerabilities must be reported privately under
[`SECURITY.md`](SECURITY.md), not through a public pull request.
