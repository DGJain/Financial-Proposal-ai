"""Prompt-history analytics rows (ui-design.md §5.A).

One analytics row per generation run, newest first: the prompt + proposal id, the
outcome tri-state, processing time, the joined financial-evidence quality (OCR /
extraction / information-loss), and the financial **context** contribution share.
The same nine-field row backs both the Prompt-History page and the dashboard's
Prompt-History Analytics table — one shape, so the two surfaces never drift.
Refused runs carry no quality (no document stage ran) and zero contribution.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.domain.generation.generation_event import GenerationEvent
from app.domain.ports.unit_of_work import UnitOfWorkPort
from app.modules.reporting.quality import FinancialQualityAggregate, aggregate_many


@dataclass(frozen=True, slots=True)
class AnalyticsRow:
    """A run plus its joined quality — the unit of the analytics table."""

    event: GenerationEvent
    quality: FinancialQualityAggregate | None


class ListPromptHistory:
    """Read use-case: a page of analytics rows over the audit log."""

    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, *, limit: int = 50, offset: int = 0) -> Sequence[AnalyticsRow]:
        async with self._uow_factory() as uow:
            events = list(await uow.audit.list_recent(limit=limit, offset=offset))
            quality_by_id = await aggregate_many(events, uow.lineage)
        return [AnalyticsRow(event=e, quality=quality_by_id[e.gen_id]) for e in events]
