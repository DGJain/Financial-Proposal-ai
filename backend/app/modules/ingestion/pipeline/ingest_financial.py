"""Open-upload entry point — ingest a user upload into ``repo_financial``.

A thin wrapper over the repository-agnostic :class:`IngestionEngine` that encodes
the open-upload governance rule (architecture §6): user uploads flow **only** into
the financial repository. It delegates to the engine with no target override, so
a document that does not classify confidently to FINANCIAL is parked for human
review rather than indexed.

The constructor and ``execute`` signatures are preserved from Phase 1 so existing
callers (the container, the upload route, the Phase 1 tests) are unaffected;
``CallerContext`` and ``IngestionRequest`` are re-exported from the engine.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.policies.classifier import DEFAULT_CLASSIFIER_POLICY, ClassifierPolicy
from app.core.policies.quality_gates import (
    DEFAULT_QUALITY_GATE_POLICY,
    QualityGatePolicy,
)
from app.domain.ingestion.lineage import IngestionResult
from app.domain.ports.embedder import EmbedderPort
from app.domain.ports.extractor import ExtractorPort
from app.domain.ports.human_review import HumanReviewQueuePort
from app.domain.ports.object_store import ObjectStorePort
from app.domain.ports.unit_of_work import UnitOfWorkPort
from app.domain.ports.vector_store import VectorStorePort
from app.modules.ingestion.pipeline.engine import (
    CallerContext,
    IngestionEngine,
    IngestionRequest,
)
from app.modules.ingestion.strategies import build_strategy_registry

__all__ = ["CallerContext", "IngestFinancialDocument", "IngestionRequest"]


class IngestFinancialDocument:
    """Use-case: ingest a user upload into ``repo_financial`` (open-upload entry)."""

    def __init__(
        self,
        *,
        extractor: ExtractorPort,
        object_store: ObjectStorePort,
        embedder: EmbedderPort,
        vector_store: VectorStorePort,
        human_review: HumanReviewQueuePort,
        uow_factory: Callable[[], UnitOfWorkPort],
        classifier_policy: ClassifierPolicy = DEFAULT_CLASSIFIER_POLICY,
        quality_policy: QualityGatePolicy = DEFAULT_QUALITY_GATE_POLICY,
    ) -> None:
        self._engine = IngestionEngine(
            extractor=extractor,
            object_store=object_store,
            embedder=embedder,
            vector_store=vector_store,
            human_review=human_review,
            uow_factory=uow_factory,
            strategies=build_strategy_registry(
                embedding_model_version=embedder.model_version,
                policy=quality_policy,
            ),
            classifier_policy=classifier_policy,
        )

    async def execute(self, request: IngestionRequest) -> IngestionResult:
        # No target override → open-upload governance (financial-only).
        return await self._engine.execute(request)
