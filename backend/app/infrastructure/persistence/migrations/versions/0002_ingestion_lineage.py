"""ingestion quality lineage — document_quality

Adds the per-document ingestion-lineage table produced by the Phase 1 financial
ingestion pipeline (classifier π_d + confidence, quality scores, gate verdict,
redaction-ledger reference). The ``document_chunks`` table already exists from
``0001`` — its read/write adapter (ChunkCatalogPort) arrives with this phase but
needs no schema change.

Revision ID: 0002_ingestion
Revises: 0001_initial
Create Date: 2026-06-06
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_ingestion"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_quality",
        sa.Column("doc_id", sa.String(64), nullable=False),
        sa.Column("repository", sa.String(16), nullable=False),
        sa.Column("pi_financial", sa.Float(), nullable=False),
        sa.Column("pi_proposal", sa.Float(), nullable=False),
        sa.Column("pi_template", sa.Float(), nullable=False),
        sa.Column("classification_confidence", sa.Float(), nullable=False),
        sa.Column("eqs", sa.Float(), nullable=False),
        sa.Column("ocr_confidence", sa.Float(), nullable=False),
        sa.Column("cfr", sa.Float(), nullable=True),
        sa.Column("rpr", sa.Float(), nullable=True),
        sa.Column("has_critical_low_confidence_region", sa.Boolean(), nullable=False),
        sa.Column("section_coverage", sa.Float(), nullable=True),
        sa.Column("placeholder_integrity", sa.Float(), nullable=True),
        sa.Column("structural_fidelity", sa.Float(), nullable=True),
        sa.Column("gate_verdict", sa.String(20), nullable=False),
        sa.Column("embedding_model_version", sa.String(64), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("ingestion_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redaction_ledger_uri", sa.String(512), nullable=True),
        sa.Column("redaction_counts", sa.JSON(), nullable=False),
        sa.Column("sensitivity", sa.JSON(), nullable=False),
        sa.Column("policy_fingerprint", sa.String(128), nullable=True),
        sa.PrimaryKeyConstraint("doc_id", name="pk_document_quality"),
        sa.ForeignKeyConstraint(
            ["doc_id"], ["documents.doc_id"],
            name="fk_document_quality_doc_id_documents",
        ),
    )
    op.create_index("ix_document_quality_repository", "document_quality", ["repository"])
    op.create_index("ix_document_quality_gate_verdict", "document_quality", ["gate_verdict"])


def downgrade() -> None:
    op.drop_table("document_quality")
