"""Repository composition metrics — the dashboard repo cards (ui-design.md §6.7).

Live, at-a-glance picture of the private knowledge base before operators trust
generation metrics: per-repository document counts, total embedded chunks, the
last successful ingestion timestamp, and the **Corpus Contribution** triple — the
share of the indexed knowledge base that lives in each repository
(document-intelligence.md U-5a). All hard-routed, so ``CC_R`` reduces to a chunk
(content-weight) share that sums to 100%.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.domain.metrics.contribution import RepositoryShare
from app.domain.ports.unit_of_work import UnitOfWorkPort
from app.domain.repositories.repository import Repository


@dataclass(frozen=True, slots=True)
class RepositoryMetricsData:
    """Counts + freshness + corpus composition of the three repositories."""

    financial_documents: int
    proposal_examples: int
    templates: int
    embedded_chunks: int
    last_ingestion_ts: datetime | None
    corpus_contribution: RepositoryShare


def _corpus_share(financial: int, proposal: int, template: int) -> RepositoryShare:
    """Chunk-weighted corpus share; template takes the residual so Σ = 100%."""
    total = financial + proposal + template
    if total == 0:
        return RepositoryShare(financial=0.0, proposal=0.0, template=0.0)
    fin = round(financial / total * 100.0, 2)
    prop = round(proposal / total * 100.0, 2)
    return RepositoryShare(financial=fin, proposal=prop, template=round(100.0 - fin - prop, 2))


class RepositoryMetrics:
    """Read use-case: corpus composition across the three repositories."""

    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self._uow_factory = uow_factory

    async def execute(self) -> RepositoryMetricsData:
        async with self._uow_factory() as uow:
            docs = {
                repo: await uow.documents.count_by_repository(repo) for repo in Repository
            }
            chunks = {
                repo: await uow.chunks.count_by_repository(repo) for repo in Repository
            }
            timestamps = [
                await uow.documents.latest_ingestion_ts(repo) for repo in Repository
            ]
        last = max((ts for ts in timestamps if ts is not None), default=None)
        return RepositoryMetricsData(
            financial_documents=docs[Repository.FINANCIAL],
            proposal_examples=docs[Repository.PROPOSAL],
            templates=docs[Repository.TEMPLATE],
            embedded_chunks=sum(chunks.values()),
            last_ingestion_ts=last,
            corpus_contribution=_corpus_share(
                chunks[Repository.FINANCIAL],
                chunks[Repository.PROPOSAL],
                chunks[Repository.TEMPLATE],
            ),
        )
