"""initial schema — catalog + generation lineage

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-06
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- documents (catalog system of record) --------------------------------
    op.create_table(
        "documents",
        sa.Column("doc_id", sa.String(64), nullable=False),
        sa.Column("repository", sa.String(16), nullable=False),
        sa.Column("subtype", sa.String(64), nullable=False),
        sa.Column("pi_financial", sa.Float(), nullable=False),
        sa.Column("pi_proposal", sa.Float(), nullable=False),
        sa.Column("pi_template", sa.Float(), nullable=False),
        sa.Column("repo_confidence", sa.Float(), nullable=False),
        sa.Column("source_uri", sa.String(512), nullable=False),
        sa.Column("file_type", sa.String(8), nullable=False),
        sa.Column("ingestion_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(16), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("acl_groups", sa.JSON(), nullable=False),
        sa.Column("engagement_id", sa.String(64), nullable=True),
        sa.Column("classification", sa.String(32), nullable=True),
        sa.Column("sensitivity", sa.JSON(), nullable=False),
        sa.Column("object_uri_versioned", sa.String(512), nullable=True),
        sa.Column("lineage_root", sa.String(64), nullable=True),
        sa.Column("parent_doc_id", sa.String(64), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("doc_id", name="pk_documents"),
        sa.ForeignKeyConstraint(
            ["parent_doc_id"], ["documents.doc_id"],
            name="fk_documents_parent_doc_id_documents",
        ),
        sa.UniqueConstraint("content_hash", name="uq_documents_content_hash"),
    )
    op.create_index("ix_documents_repository", "documents", ["repository"])
    op.create_index("ix_documents_subtype", "documents", ["subtype"])
    op.create_index("ix_documents_ingestion_ts", "documents", ["ingestion_ts"])
    op.create_index("ix_documents_engagement_id", "documents", ["engagement_id"])

    # --- document_chunks (chunk_id <-> vector_id mapping; copied ACL) ---------
    op.create_table(
        "document_chunks",
        sa.Column("chunk_id", sa.String(64), nullable=False),
        sa.Column("doc_id", sa.String(64), nullable=False),
        sa.Column("repository", sa.String(16), nullable=False),
        sa.Column("role_in_generation", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=True),
        sa.Column("embedding_model_version", sa.String(64), nullable=False),
        sa.Column("vector_id", sa.String(64), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("acl_groups", sa.JSON(), nullable=False),
        sa.Column("engagement_id", sa.String(64), nullable=True),
        sa.Column("classification", sa.String(32), nullable=True),
        sa.PrimaryKeyConstraint("chunk_id", name="pk_document_chunks"),
        sa.ForeignKeyConstraint(
            ["doc_id"], ["documents.doc_id"],
            name="fk_document_chunks_doc_id_documents",
        ),
    )
    op.create_index("ix_document_chunks_doc_id", "document_chunks", ["doc_id"])
    op.create_index("ix_document_chunks_repository", "document_chunks", ["repository"])
    op.create_index("ix_document_chunks_vector_id", "document_chunks", ["vector_id"])
    op.create_index("ix_document_chunks_engagement_id", "document_chunks", ["engagement_id"])

    # --- generation_events (immutable lineage parent) ------------------------
    op.create_table(
        "generation_events",
        sa.Column("gen_id", sa.String(64), nullable=False),
        sa.Column("engagement_id", sa.String(64), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confidence_band", sa.String(8), nullable=False),
        sa.Column("proposal_id", sa.String(64), nullable=True),
        sa.Column("refusal_reason", sa.Text(), nullable=True),
        sa.Column("policy_fingerprint", sa.String(64), nullable=True),
        sa.Column("retrieval_weights", sa.JSON(), nullable=False),
        sa.Column("ctx_financial_pct", sa.Float(), nullable=True),
        sa.Column("ctx_proposal_pct", sa.Float(), nullable=True),
        sa.Column("ctx_template_pct", sa.Float(), nullable=True),
        sa.Column("fact_financial_pct", sa.Float(), nullable=True),
        sa.Column("fact_proposal_pct", sa.Float(), nullable=True),
        sa.Column("fact_template_pct", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("gen_id", name="pk_generation_events"),
    )
    op.create_index("ix_generation_events_engagement_id", "generation_events", ["engagement_id"])
    op.create_index("ix_generation_events_ts", "generation_events", ["ts"])
    op.create_index("ix_generation_events_outcome", "generation_events", ["outcome"])
    op.create_index("ix_generation_events_proposal_id", "generation_events", ["proposal_id"])

    # --- lineage child tables (append-only) ----------------------------------
    op.create_table(
        "retrieval_hits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("gen_id", sa.String(64), nullable=False),
        sa.Column("chunk_id", sa.String(64), nullable=False),
        sa.Column("doc_id", sa.String(64), nullable=False),
        sa.Column("repository", sa.String(16), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("source_name", sa.String(256), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False),
        sa.Column("page_end", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_retrieval_hits"),
        sa.ForeignKeyConstraint(
            ["gen_id"], ["generation_events.gen_id"],
            name="fk_retrieval_hits_gen_id_generation_events",
        ),
    )
    op.create_index("ix_retrieval_hits_gen_id", "retrieval_hits", ["gen_id"])
    op.create_index("ix_retrieval_hits_repository", "retrieval_hits", ["repository"])

    op.create_table(
        "citations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("gen_id", sa.String(64), nullable=False),
        sa.Column("claim_ordinal", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.String(64), nullable=False),
        sa.Column("repository", sa.String(16), nullable=False),
        sa.Column("source_name", sa.String(256), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_citations"),
        sa.ForeignKeyConstraint(
            ["gen_id"], ["generation_events.gen_id"],
            name="fk_citations_gen_id_generation_events",
        ),
    )
    op.create_index("ix_citations_gen_id", "citations", ["gen_id"])

    op.create_table(
        "stage_timings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("gen_id", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_stage_timings"),
        sa.ForeignKeyConstraint(
            ["gen_id"], ["generation_events.gen_id"],
            name="fk_stage_timings_gen_id_generation_events",
        ),
    )
    op.create_index("ix_stage_timings_gen_id", "stage_timings", ["gen_id"])

    op.create_table(
        "gate_outcomes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("gen_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("verdict", sa.String(20), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_gate_outcomes"),
        sa.ForeignKeyConstraint(
            ["gen_id"], ["generation_events.gen_id"],
            name="fk_gate_outcomes_gen_id_generation_events",
        ),
    )
    op.create_index("ix_gate_outcomes_gen_id", "gate_outcomes", ["gen_id"])


def downgrade() -> None:
    op.drop_table("gate_outcomes")
    op.drop_table("stage_timings")
    op.drop_table("citations")
    op.drop_table("retrieval_hits")
    op.drop_table("generation_events")
    op.drop_table("document_chunks")
    op.drop_table("documents")
