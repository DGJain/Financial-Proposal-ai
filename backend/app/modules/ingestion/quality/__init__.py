"""Repository-aware quality assessment + gates."""

from app.modules.ingestion.quality.assessor import FinancialQualityAssessor
from app.modules.ingestion.quality.gate import (
    FinancialQualityGate,
    GateResult,
    ProposalQualityGate,
    TemplateQualityGate,
)
from app.modules.ingestion.quality.proposal_assessor import ProposalQualityAssessor
from app.modules.ingestion.quality.template_assessor import TemplateQualityAssessor

__all__ = [
    "FinancialQualityAssessor",
    "FinancialQualityGate",
    "GateResult",
    "ProposalQualityAssessor",
    "ProposalQualityGate",
    "TemplateQualityAssessor",
    "TemplateQualityGate",
]
