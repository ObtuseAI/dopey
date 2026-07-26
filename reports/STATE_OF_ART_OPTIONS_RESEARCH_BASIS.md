# State-of-the-Art Options Research Basis

Reviewed: 2026-07-17  
Scope: primary and authoritative sources translated into paper-research controls  
Evidence effect: design basis only; no source proves a DOPEY trading edge

## Market and lifecycle authority

- The [OCC Options Disclosure Document](https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document)
  is the controlling risk reference for standardized option characteristics,
  exercise, assignment, and product-specific risks. Ascendancy therefore requires
  contract-specific style, settlement, deliverable, adjustment, exercise, and
  assignment identity rather than inferring them from delta.
- The [Options Industry Council Greeks reference](https://www.optionseducation.org/advancedconcepts/understanding-options-greeks)
  supports explicit sensitivity decomposition. Ascendancy extends the operational
  budget beyond first-order Greeks to vanna, charm, vomma, skew, correlation, event,
  liquidity, and gap exposure; an unavailable critical exposure forces abstention.

## Surface and pricing methodology

- Cboe Hanweck documents exchange-grade
  [implied-volatility and Greek methodology](https://www.cboe.com/services/analytics/hanweck/implied_volatility/),
  including American-option modeling concerns. DOPEY does not certify its current
  European Black-Scholes path as an American lifecycle model.
- Gatheral and Jacquier's
  [arbitrage-free SVI construction](https://arxiv.org/abs/1204.0646) establishes that
  a smooth-looking volatility fit is insufficient without static-arbitrage tests.
  Surface-dislocation and skew families remain blocked until those properties and
  point-in-time reproducibility are validated.
- The [Cboe LiveVol data FAQ](https://datashop.cboe.com/faqs) distinguishes historical
  data products and quote content. This reinforces the repository rule that a
  public date-only snapshot is not a firm executable NBBO or a fill witness.

## Execution and risk controls

- Cboe's [US options FIX specification](https://www.cboe.com/document/tech-spec/document/technical-specifications/cboe-titanium-u.s.-options-fix-specification)
  exposes operational concepts such as order handling and protection controls.
  Ascendancy models none of those as realized execution; paper intent requires a
  later quote witness and remains simulated.
- The SEC's [Market Access Rule FAQ](https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions/divisionsmarketregfaq-0)
  reinforces pretrade control and direct control over market access. Ascendancy has
  no market access, credentials, or live order path and caps autonomous operation at
  paper-shadow L5.
- NIST's [FIPS 186-5 Digital Signature Standard](https://csrc.nist.gov/pubs/fips/186-5/final)
  supports cryptographic verification rather than a caller-supplied "verified" flag.
  Ascendancy verifies sealed response bodies with Ed25519 against an exact pinned
  trust record; the shipped record is intentionally `not_configured`, so no evaluator
  identity or public key is fabricated.
- Federal Reserve and OCC
  [model-risk guidance](https://www.federalreserve.gov/frrs/guidance/supervisory-guidance-on-model-risk-management.htm)
  motivates independent validation, challenger models, limitations, versioning,
  monitoring, and retirement rather than trusting complexity.

## Forecast calibration and selection-aware evidence

- Gneiting and Raftery's
  [proper scoring rule framework](https://sites.stat.washington.edu/people/raftery/Research/PDF/Gneiting2007jasa.pdf)
  supports Brier and log scoring of probabilistic forecasts rather than win rate.
- Murphy's
  [Brier score decomposition](https://journals.ametsoc.org/configurable/content/journals%24002fapme%24002f12%24002f4%24002f1520-0450_1973_012_0595_anvpot_2_0_co_2.xml)
  motivates separating reliability, resolution, and uncertainty.
- White's
  [Reality Check](https://onlinelibrary.wiley.com/doi/abs/10.1111/1468-0262.00152),
  Bailey and colleagues'
  [Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/Papers.cfm?abstract_id=2326253),
  and the
  [Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
  motivate complete trial accounting, selection-aware inference, and rejection of a
  high in-sample Sharpe as certification.
- [OSF registration guidance](https://help.osf.io/article/330-welcome-to-registrations)
  provides a practical precedent for immutable preregistration. Ascendancy freezes
  hypotheses, falsification conditions, metrics, costs, splits, and candidate hashes
  before final evaluation.

## Resulting engineering standard

An option algorithm is admissible only if its inputs were available at the decision
time; its payoff, lifecycle, and costs are explicit; its surface is defensible; its
fill is not invented; its trial belongs to a complete ledger; its probability claims
are calibrated with proper scores; its improvement survives simpler baselines,
multiple-search controls, adversarial review, and replication; and its final evidence
is sealed and prospective. Until then, it is a hypothesis or a mechanics artifact.
