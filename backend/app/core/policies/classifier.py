"""Repository-classifier routing policy.

The local classifier emits a soft distribution ``π_d = (π_FIN, π_PROP, π_TMPL)``
with Σ = 1 plus a confidence (document-intelligence.md U-1). Routing thresholds
live here so they can be tuned and recorded with lineage.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClassifierPolicy:
    """Routing thresholds for repository classification.

    - ``theta_cls``: minimum max(π_d) to hard-route; below → human review.
    - ``theta_split``: if a second repository's mass exceeds this, the document
      spans repositories and is split-routed at section level.
    """

    theta_cls: float = 0.70
    theta_split: float = 0.30


DEFAULT_CLASSIFIER_POLICY = ClassifierPolicy()
