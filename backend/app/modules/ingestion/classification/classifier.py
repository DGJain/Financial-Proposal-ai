"""Repository classifier — emits the soft distribution π_d (document-intelligence
U-1).

The production system uses a local (air-gapped) classifier model; for the Phase 1
financial vertical slice this is a deterministic lexical scorer that is good
enough to (a) always produce a real ``SoftDistribution`` for lineage and routing,
and (b) flag genuinely off-repository uploads for human review. It is swappable
for the model later behind the same call shape — the routing *policy*
(``ClassifierPolicy`` thresholds) is what the pipeline consumes, not this scorer.

Phase 1 contract: the slice hard-routes to FINANCIAL, but the emitted π_d and
``confidence = max(π_d)`` are real and recorded; when confidence is below
``theta_cls`` the document is routed to human review rather than indexed.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from app.domain.repositories.repository import Repository, SoftDistribution

_TOKEN = re.compile(r"[a-z]+")

# Indicative lexicons per repository. Deliberately small and finance-leaning;
# the real model replaces this without changing the interface.
_LEXICON: dict[Repository, frozenset[str]] = {
    Repository.FINANCIAL: frozenset({
        "revenue", "ebitda", "balance", "sheet", "income", "statement", "cash",
        "flow", "assets", "liabilities", "equity", "fiscal", "quarter", "annual",
        "report", "earnings", "dividend", "filing", "prospectus", "gaap", "audited",
        "consolidated", "net", "gross", "margin", "valuation", "shares",
    }),
    Repository.PROPOSAL: frozenset({
        "proposal", "engagement", "scope", "deliverables", "client", "approach",
        "methodology", "timeline", "case", "study", "pitch", "team", "objectives",
        "recommend", "solution", "services",
    }),
    Repository.TEMPLATE: frozenset({
        "template", "placeholder", "section", "insert", "tbd", "boilerplate",
        "heading", "structure", "outline", "fill",
    }),
}

_PRIOR: dict[Repository, float] = {
    Repository.FINANCIAL: 1.0,
    Repository.PROPOSAL: 0.6,
    Repository.TEMPLATE: 0.4,
}


@dataclass(frozen=True, slots=True)
class Classification:
    """Classifier output: the distribution plus its convenience views."""

    distribution: SoftDistribution

    @property
    def repository(self) -> Repository:
        return self.distribution.argmax

    @property
    def confidence(self) -> float:
        return self.distribution.confidence


class RepositoryClassifier:
    """Deterministic lexical classifier producing π_d over the three repositories."""

    def __init__(self, temperature: float = 4.0) -> None:
        # Lower temperature → sharper (more confident) distribution.
        self._temperature = temperature

    def classify(self, text: str) -> Classification:
        tokens = _TOKEN.findall(text.lower())
        counts = {token: 1 for token in set(tokens)}  # presence, not frequency
        raw: dict[Repository, float] = {}
        for repo, lexicon in _LEXICON.items():
            hits = sum(counts.get(word, 0) for word in lexicon)
            raw[repo] = _PRIOR[repo] * (1.0 + hits)
        dist = self._softmax(raw)
        return Classification(distribution=dist)

    def _softmax(self, raw: dict[Repository, float]) -> SoftDistribution:
        # Softmax over log-scores so the priors/hit counts combine multiplicatively
        # but the output is a proper distribution summing to 1.
        logits = {repo: math.log(max(score, 1e-9)) * self._temperature for repo, score in raw.items()}
        peak = max(logits.values())
        exps = {repo: math.exp(logit - peak) for repo, logit in logits.items()}
        total = sum(exps.values())
        return SoftDistribution(
            financial=exps[Repository.FINANCIAL] / total,
            proposal=exps[Repository.PROPOSAL] / total,
            template=exps[Repository.TEMPLATE] / total,
        )
