"""Build the Execution Report for one generation run (ui-design.md §6.6).

Reconstructs exactly what the pipeline retrieved and produced for one prompt: the
verbatim prompt, the documents retrieved from each repository with their scores,
the joined per-document quality (OCR / extraction / information-loss), the gate
verdict, the stage timeline, and the source citations. Read-only and audit-linked
— it computes nothing the run did not already record. A *refused* run still yields
a report: its prompt, zero retrieved documents, the refusal reason, and no stages.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.domain.generation.generation_event import GenerationEvent
from app.domain.ports.unit_of_work import UnitOfWorkPort
from app.modules.reporting.quality import (
    FinancialQualityAggregate,
    aggregate_financial_quality,
)


@dataclass(frozen=True, slots=True)
class ExecutionReportData:
    """A run's event plus the joined quality of its financial evidence."""

    event: GenerationEvent
    quality: FinancialQualityAggregate | None


class BuildExecutionReport:
    """Read use-case: reconstruct one run's forensic report from lineage."""

    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, gen_id: str) -> ExecutionReportData | None:
        async with self._uow_factory() as uow:
            event = await uow.audit.get(gen_id)
            if event is None:
                return None
            quality = await aggregate_financial_quality(event, uow.lineage)
        return ExecutionReportData(event=event, quality=quality)
