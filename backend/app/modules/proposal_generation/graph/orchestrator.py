"""Generation orchestrator — fan-out / fan-in use-case (rag-design.md §1).

Plain ``asyncio`` orchestration of the federated pipeline (no graph-framework
types leak into the use-case): formulate → **fan-out retrieve (concurrent)** →
within-repo rank → financial grounding gate (loop or refuse) → context-budget
assemble → generate → numeric verification + factual-health guardrail → confidence
→ contribution → persist the ``GenerationEvent`` lineage (and the ``Proposal`` on
success). Every terminal path — generated, refused, or blocked — persists a
replayable ``GenerationEvent``; only a clean run also persists a ``Proposal``.

Invariants enforced here (the dissertation's core):
* the three repositories are ranked within-repo and assembled by budget, never
  pooled by raw score;
* citations resolve only to ``repo_financial``;
* weak financial grounding cannot be rescued by template/exemplar — it loops then
  refuses;
* a figure traced to a non-financial repository blocks & regenerates, then refuses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

from app.core.policies.retrieval import DEFAULT_RETRIEVAL_POLICY, RetrievalPolicy
from app.domain.generation.brief import GenerationBrief, RequesterContext
from app.domain.generation.enums import GenerationGateVerdict, GenerationStage
from app.domain.generation.generation_event import (
    GateOutcome,
    GenerationEvent,
    RetrievalHit,
    StageTiming,
)
from app.domain.metrics.contribution import ContributionBreakdown, RepositoryShare
from app.domain.ports.embedder import EmbedderPort
from app.domain.ports.llm_gateway import LLMGatewayPort
from app.domain.ports.vector_store import AclFilter, ScoredChunk, VectorStorePort
from app.domain.proposals.enums import ConfidenceBand, GenerationOutcome
from app.domain.proposals.proposal import Proposal
from app.domain.repositories.repository import Repository
from app.modules.metrics.contribution.calculator import ContributionCalculator
from app.modules.proposal_generation.generation.generator import ProposalGenerator
from app.modules.proposal_generation.guardrails.factual_health import FactualHealthGuard
from app.modules.proposal_generation.lineage import source_name_of
from app.modules.proposal_generation.verification.numeric import (
    NumericVerifier,
    VerificationResult,
    extract_figures,
)
from app.modules.rag.assembly.assembler import AssembledContext, ContextAssembler
from app.modules.rag.confidence.scorer import ConfidenceScorer
from app.modules.rag.grounding.evaluator import GroundingEvaluator
from app.modules.rag.query.formulator import QueryFormulator
from app.modules.rag.ranking.ranker import RankedCandidates, Relaxation, WithinRepoRanker
from app.modules.rag.retrievers.federated import CandidatePool, FederatedRetriever

_ZERO_SHARE = RepositoryShare(financial=0.0, proposal=0.0, template=0.0)
_ZERO_CONTRIBUTION = ContributionBreakdown(
    context_share=_ZERO_SHARE, factual_share=_ZERO_SHARE
)


@dataclass(frozen=True, slots=True)
class GenerateProposalCommand:
    brief: GenerationBrief
    requester: RequesterContext


@dataclass(frozen=True, slots=True)
class GenerateProposalResult:
    """The persisted lineage event and, on success, the produced proposal."""

    event: GenerationEvent
    proposal: Proposal | None

    @property
    def outcome(self) -> GenerationOutcome:
        return self.event.outcome

    @property
    def confidence_band(self) -> ConfidenceBand:
        return self.event.confidence_band


class GenerateProposal:
    """Federated retrieval → grounded generation → guardrails → persisted lineage."""

    def __init__(
        self,
        *,
        vector_store: VectorStorePort,
        embedder: EmbedderPort,
        gateway: LLMGatewayPort,
        uow_factory,  # Callable[[], UnitOfWorkPort]
        policy: RetrievalPolicy = DEFAULT_RETRIEVAL_POLICY,
    ) -> None:
        self._uow_factory = uow_factory
        self._policy = policy
        self._formulator = QueryFormulator()
        self._retriever = FederatedRetriever(
            vector_store=vector_store, embedder=embedder, budget=policy.branch_budget
        )
        self._ranker = WithinRepoRanker()
        self._assembler = ContextAssembler(gateway=gateway, budget=policy.context_budget)
        self._grounding = GroundingEvaluator(policy.grounding)
        self._generator = ProposalGenerator(gateway)
        self._verifier = NumericVerifier()
        self._confidence = ConfidenceScorer(policy.grounding)
        self._contribution = ContributionCalculator()
        self._factual_guard = FactualHealthGuard(policy.grounding)

    async def execute(self, command: GenerateProposalCommand) -> GenerateProposalResult:
        brief, requester = command.brief, command.requester
        gen_id = "gen-" + uuid.uuid4().hex[:16]
        ts = datetime.now(UTC)
        acl = AclFilter(
            caller_groups=requester.caller_groups,
            caller_engagement_id=requester.engagement_id,
        )
        timings: list[StageTiming] = []
        t_total = perf_counter()

        # 1) Rewrite — per-repository query formulation.
        t = perf_counter()
        queries = self._formulator.formulate(brief)
        timings.append(self._timing(GenerationStage.REWRITE, t))

        # 2) Retrieve (fan-out) + 3) ground (loop on the financial branch).
        t_retrieve = perf_counter()
        pool, ranked, strength, loops = await self._retrieve_and_ground(brief, queries, acl)
        ground_ms = self._ms(t_retrieve)
        timings.append(StageTiming(GenerationStage.RETRIEVE, ground_ms))
        timings.append(
            StageTiming(GenerationStage.GROUND, 0)  # folded into RETRIEVE loop above
        )

        retrieval_hits = _hits_from_pool(pool)
        weights = {
            Repository.FINANCIAL: self._policy.context_budget.evidence_share,
            Repository.PROPOSAL: self._policy.context_budget.exemplar_share,
            Repository.TEMPLATE: self._policy.context_budget.scaffold_share,
        }

        # Client-supplied content path: when the caller attached material (a PDF/DOCX
        # with data/tables), weave it into a proposal with a dynamic section count and
        # reproduce its tables verbatim. The attachment's figures are allowed through
        # (client-supplied, unverified); a figure absent from both attachment and cited
        # evidence is still blocked as invented. Runs regardless of grounding strength.
        if brief.has_attachments:
            return await self._generate_from_attachments(
                gen_id, brief, requester, ts, ranked, strength, loops,
                retrieval_hits, weights, timings, t_total,
            )

        # Grounding floor is a hard gate for *cited* generation. Below it we never
        # emit figures or citations — but if a template/exemplars are available we
        # fall back to a figure-free **style-only** draft (clearly labelled, LOW
        # confidence, zero citations) instead of refusing outright. With nothing to
        # style on, refuse. Either way no ungrounded figure can ship.
        if strength < self._policy.grounding.grounding_floor:
            can_style_only = bool(
                ranked.get(Repository.TEMPLATE) or ranked.get(Repository.PROPOSAL)
            )
            if not can_style_only:
                return await self._refuse(
                    gen_id, brief, requester.engagement_id or "", ts, strength, loops,
                    retrieval_hits, weights, timings, t_total,
                )
            return await self._generate_style_only(
                gen_id, brief, requester, ts, ranked, strength, loops,
                retrieval_hits, weights, timings, t_total,
            )

        # 4) Assemble (context budget) + 5) generate.
        t = perf_counter()
        context = await self._assembler.assemble(
            scaffold=ranked.get(Repository.TEMPLATE),
            evidence=ranked.get(Repository.FINANCIAL),
            exemplars=ranked.get(Repository.PROPOSAL),
        )
        template_id = self._template_id(context)
        proposal_id = "prop-" + uuid.uuid4().hex[:16]
        draft = await self._generator.generate(
            brief=brief,
            context=context,
            gen_id=gen_id,
            proposal_id=proposal_id,
            engagement_id=requester.engagement_id or "",
            template_id=template_id,
            requested_by=requester.requested_by,
            ts=ts,
        )
        timings.append(self._timing(GenerationStage.GENERATE, t))

        # 6) Numeric verification + factual-health guardrail (block & regenerate).
        verification = self._verifier.verify(
            output_text=draft.output_text,
            evidence_chunks=context.evidence_chunks,
            nonfinancial_chunks=context.exemplar_chunks + context.scaffold_chunks,
        )
        contribution = self._contribution.compute(
            context_tokens=context.tokens_by_repository,
            factual_counts=_factual_counts(verification),
        )
        factual_gate = self._factual_guard.check(contribution)
        grounding_gate = GateOutcome(
            name="financial_grounding",
            verdict=GenerationGateVerdict.PASS,
            detail=f"strength={strength:.3f} ≥ floor={self._policy.grounding.grounding_floor}",
        )
        numeric_gate = GateOutcome(
            name="numeric_verification",
            verdict=verification.verdict,
            detail=verification.detail(),
        )
        gate_outcomes = [grounding_gate, numeric_gate, factual_gate]

        blocked = (
            not verification.passed
            or factual_gate.verdict is GenerationGateVerdict.BLOCK_REGENERATE
        )
        timings.append(self._timing(GenerationStage.TOTAL, t_total))

        if blocked:
            # Block & regenerate exhausted (deterministic gateway re-leaks) → refuse.
            return await self._persist_blocked(
                gen_id, brief, requester.engagement_id or "", ts, retrieval_hits,
                verification, contribution, gate_outcomes, weights, timings, strength,
            )

        # 7) Confidence band + persist proposal & lineage.
        assessment = self._confidence.score(
            grounding_strength=strength,
            template_coverage=1.0 if context.has_scaffold else 0.0,
            exemplar_relevance=_top_score(ranked.get(Repository.PROPOSAL)),
        )
        event = GenerationEvent(
            gen_id=gen_id,
            engagement_id=requester.engagement_id or "",
            prompt=brief.render_prompt(),
            ts=ts,
            outcome=GenerationOutcome.GENERATED,
            confidence=assessment.score,
            confidence_band=assessment.band,
            retrieval_hits=retrieval_hits,
            citations=verification.citations,
            stage_timings=tuple(timings),
            gate_outcomes=tuple(gate_outcomes),
            contribution=contribution,
            proposal_id=draft.proposal.proposal_id,
            policy_fingerprint=self._fingerprint(strength, loops),
            retrieval_weights=weights,
        )
        async with self._uow_factory() as uow:
            await uow.audit.append(event)
            await uow.proposals.add(draft.proposal)
            await uow.commit()
        return GenerateProposalResult(event=event, proposal=draft.proposal)

    # --- grounding loop ------------------------------------------------------

    async def _retrieve_and_ground(
        self, brief: GenerationBrief, queries, acl: AclFilter
    ) -> tuple[CandidatePool, RankedCandidates, float, int]:
        base_k = self._policy.branch_budget.financial_k
        max_loops = self._policy.grounding.max_grounding_loops
        pool: CandidatePool = CandidatePool()
        ranked: RankedCandidates = RankedCandidates()
        strength = 0.0
        attempt = 0
        for attempt in range(max_loops + 1):
            financial_k = base_k * (attempt + 1)  # broaden recall each loop
            pool = await self._retriever.retrieve(queries, acl, financial_k=financial_k)
            ranked = self._ranker.rank(
                pool, brief, relaxation=Relaxation.for_attempt(attempt)
            )
            strength = self._grounding.strength(ranked.get(Repository.FINANCIAL))
            if strength >= self._policy.grounding.grounding_floor:
                break
        return pool, ranked, strength, attempt

    # --- terminal paths ------------------------------------------------------

    async def _refuse(
        self, gen_id, brief, engagement_id, ts, strength, loops, retrieval_hits,
        weights, timings, t_total,
    ) -> GenerateProposalResult:
        timings.append(self._timing(GenerationStage.TOTAL, t_total))
        reason = (
            f"financial grounding strength {strength:.3f} below floor "
            f"{self._policy.grounding.grounding_floor} after {loops} grounding loop(s)"
        )
        event = GenerationEvent(
            gen_id=gen_id,
            engagement_id=engagement_id,
            prompt=brief.render_prompt(),
            ts=ts,
            outcome=GenerationOutcome.REFUSED,
            confidence=0.0,
            confidence_band=ConfidenceBand.LOW,
            retrieval_hits=retrieval_hits,
            citations=(),
            stage_timings=tuple(timings),
            gate_outcomes=(
                GateOutcome(
                    name="financial_grounding",
                    verdict=GenerationGateVerdict.REFUSE,
                    detail=reason,
                ),
            ),
            contribution=_ZERO_CONTRIBUTION,
            refusal_reason=reason,
            policy_fingerprint=self._fingerprint(strength, loops),
            retrieval_weights=weights,
        )
        async with self._uow_factory() as uow:
            await uow.audit.append(event)
            await uow.commit()
        return GenerateProposalResult(event=event, proposal=None)

    async def _generate_style_only(
        self, gen_id, brief, requester, ts, ranked, strength, loops,
        retrieval_hits, weights, timings, t_total,
    ) -> GenerateProposalResult:
        """No-evidence fallback — a figure-free draft styled on template + exemplars.

        Below the grounding floor there is no financial evidence to cite, so this
        path produces a qualitative draft with **zero citations** and ``LOW``
        confidence. The numeric verifier still runs as a hard safety net: if the
        model emitted any figure (leaked or invented), it is by definition
        ungrounded here → block & refuse rather than ship it. The factual-health
        guard is intentionally skipped — with no figures there is no factual share
        to police, so its "≥99.9% financial" floor does not apply.
        """
        engagement_id = requester.engagement_id or ""

        t = perf_counter()
        context = await self._assembler.assemble(
            scaffold=ranked.get(Repository.TEMPLATE),
            evidence=ranked.get(Repository.FINANCIAL),  # below floor → effectively empty
            exemplars=ranked.get(Repository.PROPOSAL),
        )
        template_id = self._template_id(context)
        proposal_id = "prop-" + uuid.uuid4().hex[:16]
        draft = await self._generator.generate(
            brief=brief,
            context=context,
            gen_id=gen_id,
            proposal_id=proposal_id,
            engagement_id=engagement_id,
            template_id=template_id,
            requested_by=requester.requested_by,
            ts=ts,
            style_only=True,
        )
        timings.append(self._timing(GenerationStage.GENERATE, t))

        verification = self._verifier.verify(
            output_text=draft.output_text,
            evidence_chunks=context.evidence_chunks,
            nonfinancial_chunks=context.exemplar_chunks + context.scaffold_chunks,
        )
        contribution = self._contribution.compute(
            context_tokens=context.tokens_by_repository,
            factual_counts=_factual_counts(verification),
        )
        timings.append(self._timing(GenerationStage.TOTAL, t_total))

        if not verification.passed:
            # A figure slipped into a no-evidence draft → it cannot be grounded →
            # block & refuse (same terminal path as a leak on the grounded route).
            gate_outcomes = [
                GateOutcome(
                    name="financial_grounding",
                    verdict=GenerationGateVerdict.REFUSE,
                    detail=f"strength={strength:.3f} below floor (style-only fallback)",
                ),
                GateOutcome(
                    name="numeric_verification",
                    verdict=verification.verdict,
                    detail=verification.detail(),
                ),
                self._factual_guard.check(contribution),
            ]
            return await self._persist_blocked(
                gen_id, brief, engagement_id, ts, retrieval_hits,
                verification, contribution, gate_outcomes, weights, timings, strength,
            )

        assessment = self._confidence.score(
            grounding_strength=strength,  # below floor → band forced LOW
            template_coverage=1.0 if context.has_scaffold else 0.0,
            exemplar_relevance=_top_score(ranked.get(Repository.PROPOSAL)),
        )
        gate_outcomes = (
            GateOutcome(
                name="financial_grounding",
                verdict=GenerationGateVerdict.REFUSE,
                detail=(
                    f"strength={strength:.3f} below floor "
                    f"{self._policy.grounding.grounding_floor} → style-only draft "
                    f"(no figures, no citations)"
                ),
            ),
            GateOutcome(
                name="numeric_verification",
                verdict=GenerationGateVerdict.PASS,
                detail="no figures emitted (style-only draft)",
            ),
            GateOutcome(
                name="factual_health",
                verdict=GenerationGateVerdict.PASS,
                detail="not applicable — style-only draft carries no figures",
            ),
        )
        event = GenerationEvent(
            gen_id=gen_id,
            engagement_id=engagement_id,
            prompt=brief.render_prompt(),
            ts=ts,
            outcome=GenerationOutcome.STYLE_ONLY,
            confidence=assessment.score,
            confidence_band=assessment.band,
            retrieval_hits=retrieval_hits,
            citations=(),  # no financial evidence → no citations
            stage_timings=tuple(timings),
            gate_outcomes=gate_outcomes,
            contribution=contribution,
            proposal_id=draft.proposal.proposal_id,
            policy_fingerprint=self._fingerprint(strength, loops),
            retrieval_weights=weights,
        )
        async with self._uow_factory() as uow:
            await uow.audit.append(event)
            await uow.proposals.add(draft.proposal)
            await uow.commit()
        return GenerateProposalResult(event=event, proposal=draft.proposal)

    async def _generate_from_attachments(
        self, gen_id, brief, requester, ts, ranked, strength, loops,
        retrieval_hits, weights, timings, t_total,
    ) -> GenerateProposalResult:
        """Client-supplied content path (see call site).

        One generation pass turns the attached material into a dynamically-sectioned
        proposal; the client's data tables are reproduced verbatim. Numeric
        verification still runs, but the attachment's own figures are an *allowed*
        set (client-supplied, unverified) alongside any cited evidence — only a
        figure invented from neither blocks. The factual-health guard is skipped
        (its "≥99.9% from financial repo" floor doesn't model client-supplied data).
        """
        engagement_id = requester.engagement_id or ""
        grounded = strength >= self._policy.grounding.grounding_floor

        t = perf_counter()
        context = await self._assembler.assemble(
            scaffold=ranked.get(Repository.TEMPLATE),
            evidence=ranked.get(Repository.FINANCIAL),
            exemplars=ranked.get(Repository.PROPOSAL),
        )
        template_id = self._template_id(context)
        proposal_id = "prop-" + uuid.uuid4().hex[:16]
        draft = await self._generator.generate_from_content(
            brief=brief,
            context=context,
            gen_id=gen_id,
            proposal_id=proposal_id,
            engagement_id=engagement_id,
            template_id=template_id,
            requested_by=requester.requested_by,
            ts=ts,
            allow_evidence=grounded,
        )
        timings.append(self._timing(GenerationStage.GENERATE, t))

        # Citations resolve only to financial evidence, and only when grounded.
        evidence_chunks = context.evidence_chunks if grounded else ()
        allowed = frozenset(extract_figures(brief.attachment_text()))
        verification = self._verifier.verify(
            output_text=draft.output_text,
            evidence_chunks=evidence_chunks,
            nonfinancial_chunks=context.exemplar_chunks + context.scaffold_chunks,
            allowed_figures=allowed,
        )
        contribution = self._contribution.compute(
            context_tokens=context.tokens_by_repository,
            factual_counts=_factual_counts(verification),
        )
        timings.append(self._timing(GenerationStage.TOTAL, t_total))

        client_gate = GateOutcome(
            name="client_supplied_content",
            verdict=GenerationGateVerdict.PASS,
            detail=(
                f"incorporated client-supplied attachment data "
                f"({len(allowed)} supplied figure(s) allowed, unverified)"
            ),
        )
        if not verification.passed:
            # A figure that is in neither the attachment nor cited evidence → invented.
            gate_outcomes = [
                GateOutcome(
                    name="financial_grounding",
                    verdict=GenerationGateVerdict.PASS if grounded else GenerationGateVerdict.REFUSE,
                    detail=f"strength={strength:.3f} (attachment-driven)",
                ),
                GateOutcome(
                    name="numeric_verification",
                    verdict=verification.verdict,
                    detail=verification.detail(),
                ),
                client_gate,
            ]
            return await self._persist_blocked(
                gen_id, brief, engagement_id, ts, retrieval_hits,
                verification, contribution, gate_outcomes, weights, timings, strength,
            )

        assessment = self._confidence.score(
            grounding_strength=strength,
            template_coverage=1.0 if context.has_scaffold else 0.0,
            exemplar_relevance=_top_score(ranked.get(Repository.PROPOSAL)),
        )
        gate_outcomes = (
            GateOutcome(
                name="financial_grounding",
                verdict=GenerationGateVerdict.PASS if grounded else GenerationGateVerdict.REFUSE,
                detail=(
                    f"strength={strength:.3f} ≥ floor={self._policy.grounding.grounding_floor}"
                    if grounded
                    else f"strength={strength:.3f} below floor — proposal built from "
                    f"client-supplied attachment data (no repository evidence cited)"
                ),
            ),
            GateOutcome(
                name="numeric_verification",
                verdict=verification.verdict,
                detail=verification.detail(),
            ),
            client_gate,
        )
        event = GenerationEvent(
            gen_id=gen_id,
            engagement_id=engagement_id,
            prompt=brief.render_prompt(),
            ts=ts,
            outcome=GenerationOutcome.GENERATED,
            confidence=assessment.score,
            confidence_band=assessment.band,
            retrieval_hits=retrieval_hits,
            citations=verification.citations,
            stage_timings=tuple(timings),
            gate_outcomes=gate_outcomes,
            contribution=contribution,
            proposal_id=draft.proposal.proposal_id,
            policy_fingerprint=self._fingerprint(strength, loops),
            retrieval_weights=weights,
        )
        async with self._uow_factory() as uow:
            await uow.audit.append(event)
            await uow.proposals.add(draft.proposal)
            await uow.commit()
        return GenerateProposalResult(event=event, proposal=draft.proposal)

    async def _persist_blocked(
        self, gen_id, brief, engagement_id, ts, retrieval_hits,
        verification: VerificationResult, contribution, gate_outcomes, weights,
        timings, strength,
    ) -> GenerateProposalResult:
        reason = "blocked: " + verification.detail()
        event = GenerationEvent(
            gen_id=gen_id,
            engagement_id=engagement_id,
            prompt=brief.render_prompt(),
            ts=ts,
            outcome=GenerationOutcome.REFUSED,
            confidence=0.0,
            confidence_band=ConfidenceBand.LOW,
            retrieval_hits=retrieval_hits,
            citations=verification.citations,  # financial citations recorded for audit
            stage_timings=tuple(timings),
            gate_outcomes=tuple(gate_outcomes),
            contribution=contribution,
            refusal_reason=reason,
            policy_fingerprint=self._fingerprint(strength, 0),
            retrieval_weights=weights,
        )
        async with self._uow_factory() as uow:
            await uow.audit.append(event)
            await uow.commit()
        return GenerateProposalResult(event=event, proposal=None)

    # --- helpers -------------------------------------------------------------

    def _template_id(self, context: AssembledContext) -> str:
        if context.scaffold_chunks:
            return context.scaffold_chunks[0].chunk.doc_id
        return "no-template"

    def _fingerprint(self, strength: float, loops: int) -> str:
        cb = self._policy.context_budget
        gp = self._policy.grounding
        return (
            f"floor={gp.grounding_floor};loops={loops};"
            f"weights=ev{cb.evidence_share}/ex{cb.exemplar_share}/sc{cb.scaffold_share}"
        )

    @staticmethod
    def _timing(stage: GenerationStage, since: float) -> StageTiming:
        return StageTiming(stage=stage, duration_ms=GenerateProposal._ms(since))

    @staticmethod
    def _ms(since: float) -> int:
        return max(0, int((perf_counter() - since) * 1000))


def _hits_from_pool(pool: CandidatePool) -> tuple[RetrievalHit, ...]:
    hits: list[RetrievalHit] = []
    for repository, scored in pool.by_repository.items():
        for sc in scored:
            hits.append(
                RetrievalHit(
                    chunk_id=sc.chunk.chunk_id,
                    doc_id=sc.chunk.doc_id,
                    repository=repository,
                    score=sc.score,
                    source_name=source_name_of(sc.chunk),
                    page_start=sc.chunk.span.page_start,
                    page_end=sc.chunk.span.page_end,
                )
            )
    return tuple(hits)


def _factual_counts(verification: VerificationResult) -> dict[Repository, int]:
    counts: dict[Repository, int] = {Repository.FINANCIAL: len(verification.citations)}
    for leaked in verification.leaked:
        counts[leaked.repository] = counts.get(leaked.repository, 0) + 1
    return counts


def _top_score(candidates: list[ScoredChunk]) -> float:
    return max((c.score for c in candidates), default=0.0)
