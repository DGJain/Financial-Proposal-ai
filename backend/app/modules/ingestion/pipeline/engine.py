"""Repository-agnostic ingestion engine (Phase 2).

Generalizes the Phase 1 financial orchestrator to all three repositories by
dispatching the four repository-specific concerns to a
``RepositoryIngestionStrategy`` (document-intelligence U-1):

    extract → normalize + redact → classify (π_d) → [route] → assess → gate
    → metadata → chunk → embed → index → persist (Document + chunks + lineage)

Governance the engine enforces (architecture §6):

* **Open uploads are financial-only.** A request with no ``target_override`` must
  classify confidently to FINANCIAL or it is parked for review — user uploads can
  never reach the curated proposal/template repositories.
* **Curated exemplars are anonymization-verified.** When routing to PROPOSAL, the
  normalized document is checked for engagement-specific leakage (figures, PII,
  MNPI, client identifiers); any finding blocks indexing.
* **Gate before index / idempotent / auditable** — unchanged from Phase 1.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from app.core.policies.classifier import DEFAULT_CLASSIFIER_POLICY, ClassifierPolicy
from app.domain.documents.acl import AccessControl
from app.domain.documents.document import Document, Provenance
from app.domain.documents.enums import FileType
from app.domain.generation.enums import QualityGateVerdict
from app.domain.ingestion.enums import IngestionStatus, ReviewReason
from app.domain.ingestion.lineage import (
    HumanReviewItem,
    IngestionLineage,
    IngestionResult,
)
from app.domain.ingestion.redaction import RedactionLedger
from app.domain.ports.embedder import EmbedderPort
from app.domain.ports.extractor import ExtractorPort
from app.domain.ports.human_review import HumanReviewQueuePort
from app.domain.ports.object_store import ObjectStorePort
from app.domain.ports.unit_of_work import UnitOfWorkPort
from app.domain.ports.vector_store import VectorStorePort
from app.domain.repositories.repository import Repository
from app.modules.ingestion.classification.classifier import Classification, RepositoryClassifier
from app.modules.ingestion.contracts import RepositoryIngestionStrategy
from app.modules.ingestion.curation.anonymization import AnonymizationVerifier
from app.modules.ingestion.embedding.indexer import EmbedAndIndex
from app.modules.ingestion.normalization.redactor import Redactor

_CONTENT_TYPES: dict[FileType, str] = {
    FileType.PDF: "application/pdf",
    FileType.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    FileType.PPTX: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    FileType.PNG: "image/png",
    FileType.JPG: "image/jpeg",
}


@dataclass(frozen=True, slots=True)
class CallerContext:
    """The uploading caller's grants, stamped onto the document's ACL."""

    acl_groups: frozenset[str] = field(default_factory=frozenset)
    engagement_id: str | None = None
    classification: str | None = None


@dataclass(frozen=True, slots=True)
class IngestionRequest:
    """One source to ingest. ``metadata_hints`` supply facts text can't reveal
    (e.g. a proposal's ``outcome``); ``known_identifiers`` are engagement entities
    the anonymization verifier must ensure are absent from an exemplar."""

    data: bytes
    filename: str
    file_type: FileType
    caller: CallerContext = field(default_factory=CallerContext)
    metadata_hints: Mapping[str, str] = field(default_factory=dict)
    known_identifiers: frozenset[str] = field(default_factory=frozenset)


class IngestionEngine:
    """The repository-agnostic ingestion orchestrator."""

    def __init__(
        self,
        *,
        extractor: ExtractorPort,
        object_store: ObjectStorePort,
        embedder: EmbedderPort,
        vector_store: VectorStorePort,
        human_review: HumanReviewQueuePort,
        uow_factory: Callable[[], UnitOfWorkPort],
        strategies: Mapping[Repository, RepositoryIngestionStrategy],
        classifier_policy: ClassifierPolicy = DEFAULT_CLASSIFIER_POLICY,
    ) -> None:
        self._extractor = extractor
        self._object_store = object_store
        self._human_review = human_review
        self._uow_factory = uow_factory
        self._strategies = strategies
        self._classifier_policy = classifier_policy

        self._redactor = Redactor()
        self._classifier = RepositoryClassifier()
        self._verifier = AnonymizationVerifier()
        self._indexer = EmbedAndIndex(embedder=embedder, vector_store=vector_store)

    async def execute(
        self,
        request: IngestionRequest,
        *,
        target_override: Repository | None = None,
    ) -> IngestionResult:
        content_hash = "sha256:" + hashlib.sha256(request.data).hexdigest()
        doc_id = "doc-" + content_hash.removeprefix("sha256:")[:16]

        # 1) Idempotency.
        async with self._uow_factory() as uow:
            if await uow.documents.exists_by_content_hash(content_hash):
                return IngestionResult(IngestionStatus.SKIPPED_DUPLICATE, doc_id)

        # 2) Persist raw original.
        content_type = _CONTENT_TYPES.get(request.file_type, "application/octet-stream")
        source_uri = await self._object_store.put_raw(
            f"{doc_id}/{request.filename}", request.data, content_type=content_type
        )

        # 3) Extract → 4) normalize + redact → 5) classify.
        extracted = await self._extractor.extract(request.data, file_type=request.file_type)
        normalized = self._redactor.normalize(extracted)
        ledger = normalized.redaction
        doc_model = normalized.document
        classification = self._classifier.classify(doc_model.full_text)
        ts = datetime.now(UTC)

        # 6) Routing: open uploads are financial-only; curated content uses its
        #    declared target.
        is_open_upload = target_override is None
        target = target_override or Repository.FINANCIAL
        strategy = self._strategies[target]

        # 7) Assess (stamp classifier confidence so the proposal soft gate sees it).
        scores = replace(
            strategy.assess(doc_model),
            classification_confidence=classification.confidence,
        )

        # 8) Governance guard — open uploads must be confidently financial.
        if is_open_upload and (
            classification.repository is not Repository.FINANCIAL
            or classification.confidence < self._classifier_policy.theta_cls
        ):
            return await self._route_to_review(
                doc_id, target, ReviewReason.LOW_CLASSIFIER_CONFIDENCE, source_uri, ts,
                classification, scores,
                detail=f"argmax={classification.repository.value}, "
                f"confidence={classification.confidence:.3f}, "
                f"theta_cls={self._classifier_policy.theta_cls}",
            )

        # 9) Anonymization verification for exemplar curation (leakage guard).
        if target is Repository.PROPOSAL:
            report = self._verifier.verify(doc_model, known_identifiers=request.known_identifiers)
            if not report.is_clean:
                return await self._route_to_review(
                    doc_id, target, ReviewReason.ANONYMIZATION_FAILED, source_uri, ts,
                    classification, scores,
                    detail=f"anonymization findings: {report.summary()}",
                )

        # 10) Repo-aware quality gate.
        gate_result = strategy.gate(scores)
        if not gate_result.approved:
            return await self._route_to_review(
                doc_id, target, ReviewReason.QUALITY_GATE_FAILED, source_uri, ts,
                classification, scores,
                gate_verdict=gate_result.verdict, detail=gate_result.reason,
            )

        # 11) Metadata → chunk → embed + index → persist.
        metadata = strategy.extract_metadata(doc_model, hints=request.metadata_hints)
        access = AccessControl(
            acl_groups=request.caller.acl_groups,
            engagement_id=request.caller.engagement_id,
            classification=request.caller.classification,
        )
        chunks = strategy.chunk(doc_model, doc_id=doc_id, access=access, metadata=metadata)
        indexed = await self._indexer.run(target, chunks)

        ledger_uri = await self._store_ledger(doc_id, ledger)
        document = Document(
            doc_id=doc_id,
            repository=target,
            subtype=metadata.subtype_value,
            provenance=Provenance(
                source_uri=source_uri,
                file_type=request.file_type,
                ingestion_ts=ts,
                page_count=doc_model.page_count,
                language=doc_model.language,
                content_hash=content_hash,
            ),
            access=access,
            soft_distribution=classification.distribution,
            repo_confidence=classification.confidence,
            sensitivity=ledger.sensitivity_flags(),
            lineage_root=f"ingest:{doc_id}",
        )
        lineage = IngestionLineage(
            doc_id=doc_id,
            repository=target,
            soft_distribution=classification.distribution,
            classification_confidence=classification.confidence,
            quality=scores,
            gate_verdict=gate_result.verdict,
            embedding_model_version=self._indexer.embedder.model_version,
            chunk_count=len(indexed),
            ingestion_ts=ts,
            redaction_ledger_uri=ledger_uri,
            redaction_counts={k.value: v for k, v in ledger.counts_by_kind().items()},
            sensitivity=ledger.sensitivity_flags(),
            policy_fingerprint=self._policy_fingerprint(target),
        )

        async with self._uow_factory() as uow:
            await uow.documents.add(document)
            await uow.chunks.add_many(indexed)
            await uow.lineage.add(lineage)
            await uow.commit()

        return IngestionResult(
            status=IngestionStatus.INDEXED,
            doc_id=doc_id,
            repository=target,
            chunk_count=len(indexed),
            gate_verdict=gate_result.verdict,
            quality=scores,
        )

    # --- helpers -------------------------------------------------------------

    async def _route_to_review(
        self,
        doc_id: str,
        repository: Repository,
        reason: ReviewReason,
        source_uri: str,
        ts: datetime,
        classification: Classification,
        scores,  # type: ignore[no-untyped-def]
        *,
        gate_verdict: QualityGateVerdict | None = None,
        detail: str | None = None,
    ) -> IngestionResult:
        verdict = gate_verdict or QualityGateVerdict.HUMAN_REVIEW
        await self._human_review.enqueue(
            HumanReviewItem(
                doc_id=doc_id,
                reason=reason,
                gate_verdict=verdict,
                quality=scores,
                soft_distribution=classification.distribution,
                classification_confidence=classification.confidence,
                source_uri=source_uri,
                queued_ts=ts,
                detail=detail,
            )
        )
        return IngestionResult(
            status=IngestionStatus.ROUTED_TO_REVIEW,
            doc_id=doc_id,
            repository=repository,
            gate_verdict=verdict,
            quality=scores,
            review_reason=reason,
        )

    async def _store_ledger(self, doc_id: str, ledger: RedactionLedger) -> str | None:
        if ledger.count == 0:
            return None
        payload = json.dumps(
            [
                {
                    "kind": e.kind.value,
                    "pattern_name": e.pattern_name,
                    "page": e.page,
                    "span_start": e.span_start,
                    "span_end": e.span_end,
                    "placeholder": e.placeholder,
                }
                for e in ledger.entries
            ]
        ).encode("utf-8")
        return await self._object_store.put_versioned(
            f"{doc_id}/redaction-ledger.json", payload, content_type="application/json"
        )

    def _policy_fingerprint(self, target: Repository) -> str:
        return f"cls:theta={self._classifier_policy.theta_cls};repo={target.value}"
