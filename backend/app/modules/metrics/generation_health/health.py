"""Generation-health aggregates over a rolling window (ui-design.md Page 4 §2).

The dashboard's generation-health zone: four headline stat cards (avg confidence,
avg extraction quality, refusal rate, proposals produced), a per-day run bar chart
over the window, and an information-loss distribution donut. All derived from the
append-only audit log via ``list_since`` plus the per-run financial-quality join,
batched so the whole window costs two reads (events + their documents' quality).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import fmean

from app.domain.generation.generation_event import GenerationEvent
from app.domain.ports.unit_of_work import UnitOfWorkPort
from app.domain.proposals.enums import GenerationOutcome
from app.modules.reporting.quality import FinancialQualityAggregate, aggregate_many

# Information-loss donut buckets. The 10% boundary is the financial extraction
# gate ceiling (EQS ≥ 0.90 ⇒ loss ≤ 10%); runs leaning on higher-loss evidence
# land in "high".
_LOW_MAX = 5.0
_MEDIUM_MAX = 10.0


@dataclass(frozen=True, slots=True)
class DailyBar:
    """Run counts for one day of the window (chart x-axis)."""

    day: date
    generated: int
    refused: int


@dataclass(frozen=True, slots=True)
class InfoLossBucket:
    label: str  # "low" | "medium" | "high"
    count: int


@dataclass(frozen=True, slots=True)
class GenerationHealthData:
    window_days: int
    runs_total: int
    proposals_generated: int
    refusal_rate: float  # fraction in [0, 1]
    avg_confidence: float
    avg_extraction_quality: float
    daily: tuple[DailyBar, ...]
    info_loss_distribution: tuple[InfoLossBucket, ...]


def _bucket(loss_pct: float) -> str:
    if loss_pct < _LOW_MAX:
        return "low"
    if loss_pct <= _MEDIUM_MAX:
        return "medium"
    return "high"


def _build(
    events: Sequence[GenerationEvent],
    quality_by_id: dict[str, FinancialQualityAggregate | None],
    *,
    days: int,
    now: datetime,
) -> GenerationHealthData:
    total = len(events)
    refused = sum(1 for e in events if e.outcome is GenerationOutcome.REFUSED)
    generated = sum(1 for e in events if e.outcome is GenerationOutcome.GENERATED)

    aggregates = [q for q in quality_by_id.values() if q is not None]

    # Per-day run counts across the inclusive window [today-(days-1), today].
    today = now.date()
    counts: dict[date, list[int]] = {
        today - timedelta(days=offset): [0, 0] for offset in range(days)
    }
    for event in events:
        ts = event.ts if event.ts.tzinfo else event.ts.replace(tzinfo=timezone.utc)
        day = ts.astimezone(timezone.utc).date()
        if day in counts:
            if event.outcome is GenerationOutcome.REFUSED:
                counts[day][1] += 1
            else:
                counts[day][0] += 1
    daily = tuple(
        DailyBar(day=day, generated=counts[day][0], refused=counts[day][1])
        for day in sorted(counts)
    )

    buckets = {"low": 0, "medium": 0, "high": 0}
    for agg in aggregates:
        buckets[_bucket(agg.information_loss_pct)] += 1

    return GenerationHealthData(
        window_days=days,
        runs_total=total,
        proposals_generated=generated,
        refusal_rate=round(refused / total, 4) if total else 0.0,
        avg_confidence=round(fmean(e.confidence for e in events), 4) if total else 0.0,
        avg_extraction_quality=(
            round(fmean(a.extraction_quality for a in aggregates), 4) if aggregates else 0.0
        ),
        daily=daily,
        info_loss_distribution=tuple(
            InfoLossBucket(label=label, count=buckets[label])
            for label in ("low", "medium", "high")
        ),
    )


class GenerationHealth:
    """Read use-case: generation-health aggregates over the last ``days`` days."""

    def __init__(self, uow_factory: Callable[[], UnitOfWorkPort]) -> None:
        self._uow_factory = uow_factory

    async def execute(self, *, days: int = 7) -> GenerationHealthData:
        days = max(1, days)
        now = datetime.now(timezone.utc)
        since = now - timedelta(days=days)
        async with self._uow_factory() as uow:
            events = list(await uow.audit.list_since(since))
            quality_by_id = await aggregate_many(events, uow.lineage)
        return _build(events, quality_by_id, days=days, now=now)
