"""Document-level vocabulary: file types, sensitivity, and per-repository subtypes.

Subtypes become filterable catalog/ChromaDB metadata (document-intelligence.md
U-2). They are grouped per repository because each repository has a distinct
taxonomy.
"""

from __future__ import annotations

from enum import StrEnum


class FileType(StrEnum):
    """Supported upload/source formats (PROJECT_CONTEXT.md "Supported Files")."""

    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    PNG = "png"
    JPG = "jpg"


class SensitivityFlag(StrEnum):
    """Sensitivity markers detected at ingestion; drive redaction + ACL.

    Material Non-Public Information (MNPI) is the finance-critical class whose
    leakage across engagements the whole architecture is designed to prevent.
    """

    PII = "pii"
    MNPI = "mnpi"


class FinancialSubtype(StrEnum):
    """`repo_financial` document subtypes (the evidence corpus)."""

    ANNUAL_REPORT = "annual_report"
    FINANCIAL_STATEMENT = "financial_statement"
    INVESTMENT_REPORT = "investment_report"
    REGULATORY_FILING = "regulatory_filing"  # e.g. 10-K
    TERM_SHEET = "term_sheet"
    RESEARCH = "research"
    PROSPECTUS = "prospectus"
    CREDIT_MEMO = "credit_memo"
    USER_UPLOAD = "user_upload"


class ProposalSubtype(StrEnum):
    """`repo_proposals` document subtypes (the exemplar corpus)."""

    PAST_PROPOSAL = "past_proposal"
    CASE_STUDY = "case_study"
    STATEMENT_OF_WORK = "statement_of_work"
    PITCH = "pitch"
    METHODOLOGY = "methodology"


class TemplateSubtype(StrEnum):
    """`repo_templates` document subtypes (the scaffold corpus)."""

    EXECUTIVE_SUMMARY = "executive_summary"
    PROPOSAL_STRUCTURE = "proposal_structure"
    PRICING = "pricing"
    TIMELINE = "timeline"
    RISK_ASSESSMENT = "risk_assessment"
