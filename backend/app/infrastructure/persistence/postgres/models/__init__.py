"""ORM models. Importing this package registers every table on ``Base.metadata``
(required by Alembic autogenerate and ``create_all`` in tests)."""

from app.infrastructure.persistence.postgres.models.document import (
    DocumentChunkRow,
    DocumentQualityRow,
    DocumentRow,
)
from app.infrastructure.persistence.postgres.models.generation import (
    CitationRow,
    GateOutcomeRow,
    GenerationEventRow,
    RetrievalHitRow,
    StageTimingRow,
)
from app.infrastructure.persistence.postgres.models.proposal import (
    ProposalRow,
    ProposalSectionRow,
    ProposalVersionRow,
)

__all__ = [
    "CitationRow",
    "DocumentChunkRow",
    "DocumentQualityRow",
    "DocumentRow",
    "GateOutcomeRow",
    "GenerationEventRow",
    "ProposalRow",
    "ProposalSectionRow",
    "ProposalVersionRow",
    "RetrievalHitRow",
    "StageTimingRow",
]
