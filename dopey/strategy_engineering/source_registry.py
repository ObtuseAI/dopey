"""Primary-source registry for the strategy-engineering design."""

from __future__ import annotations

from typing import Final

from .schema import SourceRecord


PRIMARY_SOURCES: Final[tuple[SourceRecord, ...]] = (
    {"source_id": "rd-agent-quant", "title": "R&D-Agent-Quant", "url": "https://arxiv.org/abs/2505.15155", "source_type": "primary_paper", "adopted_capability": "separate research and development loops with factor-model feedback", "evidence_restriction": "paper performance claims are not DOPEY evidence"},
    {"source_id": "rd-agent-repository", "title": "Microsoft RD-Agent", "url": "https://github.com/microsoft/RD-Agent", "source_type": "official_repository", "adopted_capability": "research orchestration patterns", "evidence_restriction": "external code and outputs receive no promotion authority"},
    {"source_id": "alphaforge", "title": "AlphaForge", "url": "https://arxiv.org/abs/2406.18394", "source_type": "primary_paper", "adopted_capability": "interpretable formulaic factors, diversity, and dynamic combination", "evidence_restriction": "reported returns are not imported as evidence"},
    {"source_id": "autoalpha", "title": "AutoAlpha", "url": "https://arxiv.org/abs/2002.08245", "source_type": "primary_paper", "adopted_capability": "hierarchical evolutionary search and quality diversity", "evidence_restriction": "all candidates require independent protected evaluation"},
    {"source_id": "alphaevolve-factor-mining", "title": "AlphaEvolve", "url": "https://arxiv.org/abs/2103.16196", "source_type": "primary_paper", "adopted_capability": "relational factor operators and redundancy pruning", "evidence_restriction": "relationships remain hypotheses until held-out settlement"},
    {"source_id": "alphaformer", "title": "AlphaFormer", "url": "https://proceedings.mlr.press/v328/huang26a.html", "source_type": "primary_paper", "adopted_capability": "end-to-end symbolic factor generation", "evidence_restriction": "generated expressions must remain interpretable and replayable"},
    {"source_id": "llm-symbolic-regression", "title": "LLM-SRBench", "url": "https://proceedings.mlr.press/v267/shojaee25a.html", "source_type": "primary_paper", "adopted_capability": "symbolic-regression proposal generation", "evidence_restriction": "language models may propose but never verify equations"},
    {"source_id": "deflated-sharpe", "title": "The Deflated Sharpe Ratio", "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551", "source_type": "primary_paper", "adopted_capability": "selection-bias and non-normality adjustment", "evidence_restriction": "required diagnostic, never a standalone promotion proof"},
    {"source_id": "pbo", "title": "The Probability of Backtest Overfitting", "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253", "source_type": "primary_paper", "adopted_capability": "combinatorially symmetric cross-validation and overfit risk", "evidence_restriction": "historical evidence remains distinct from forward proof"},
    {"source_id": "confidence-sequences", "title": "Time-uniform, nonparametric, nonasymptotic confidence sequences", "url": "https://arxiv.org/abs/1810.08240", "source_type": "primary_paper", "adopted_capability": "anytime-valid monitoring", "evidence_restriction": "implemented bounds must state their exact assumptions"},
    {"source_id": "online-fdr", "title": "SAFFRON", "url": "https://arxiv.org/abs/1802.09098", "source_type": "primary_paper", "adopted_capability": "online false-discovery control", "evidence_restriction": "DOPEY currently uses conservative alpha spending, not a claimed SAFFRON implementation"},
    {"source_id": "conformal-risk-control", "title": "Conformal Risk Control", "url": "https://arxiv.org/abs/2208.02814", "source_type": "primary_paper", "adopted_capability": "distribution-free risk-controlled abstention", "evidence_restriction": "coverage claims require exchangeability and adequate calibration data"},
    {"source_id": "adaptive-conformal-risk-control", "title": "Adaptive Conformal Risk Control", "url": "https://proceedings.mlr.press/v258/blot25a.html", "source_type": "primary_paper", "adopted_capability": "risk control under changing environments", "evidence_restriction": "regime drift triggers abstention rather than assumed coverage"},
    {"source_id": "pairs-trading", "title": "Pairs Trading: Performance of a Relative-Value Arbitrage Rule", "url": "https://academic.oup.com/rfs/article-abstract/19/3/797/1646694", "source_type": "primary_paper", "adopted_capability": "relative-value mechanism templates", "evidence_restriction": "costs, borrow, selection, and regime transfer must be retested"},
    {"source_id": "momentum-crashes", "title": "Momentum Crashes", "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2490306", "source_type": "primary_paper", "adopted_capability": "crash-state guards for momentum", "evidence_restriction": "guard behavior requires point-in-time regime inputs"},
    {"source_id": "change-point", "title": "Sequential change-point detection in financial markets", "url": "https://arxiv.org/abs/2407.16376", "source_type": "primary_paper", "adopted_capability": "online regime-break hypotheses", "evidence_restriction": "detectors may route or abstain but cannot rewrite settled truth"},
    {"source_id": "multifactor-timing", "title": "Multifactor timing", "url": "https://academic.oup.com/jfec/article/24/3/nbag006/8658726", "source_type": "primary_paper", "adopted_capability": "state-conditioned factor allocation hypotheses", "evidence_restriction": "publication results are not forward DOPEY proof"},
)


def source_ids() -> frozenset[str]:
    return frozenset(record["source_id"] for record in PRIMARY_SOURCES)
