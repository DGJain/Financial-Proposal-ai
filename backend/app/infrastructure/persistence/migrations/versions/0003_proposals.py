"""proposal aggregate — proposals, versions, sections

Adds persistence for the generated proposal document (Phase 3): the aggregate
root, its immutable version snapshots, and the ordered sections bound to template
slots. The ``GenerationEvent`` lineage tables already exist from ``0001``; this
migration adds only the produced-document side.

Revision ID: 0003_proposals
Revises: 0002_ingestion
Create Date: 2026-06-06
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_proposals"
down_revision: str | None = "0002_ingestion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposals",
        sa.Column("proposal_id", sa.String(64), nullable=False),
        sa.Column("gen_id", sa.String(64), nullable=False),
        sa.Column("engagement_id", sa.String(64), nullable=False),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint("proposal_id", name="pk_proposals"),
    )
    op.create_index("ix_proposals_gen_id", "proposals", ["gen_id"])
    op.create_index("ix_proposals_engagement_id", "proposals", ["engagement_id"])
    op.create_index("ix_proposals_status", "proposals", ["status"])

    op.create_table(
        "proposal_versions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("proposal_id", sa.String(64), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("created_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_proposal_versions"),
        sa.ForeignKeyConstraint(
            ["proposal_id"], ["proposals.proposal_id"],
            name="fk_proposal_versions_proposal_id_proposals",
        ),
    )
    op.create_index(
        "ix_proposal_versions_proposal_id", "proposal_versions", ["proposal_id"]
    )

    op.create_table(
        "proposal_sections",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.String(80), nullable=False),
        sa.Column("slot", sa.String(64), nullable=False),
        sa.Column("heading", sa.String(256), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_proposal_sections"),
        sa.ForeignKeyConstraint(
            ["version_id"], ["proposal_versions.id"],
            name="fk_proposal_sections_version_id_proposal_versions",
        ),
    )
    op.create_index(
        "ix_proposal_sections_version_id", "proposal_sections", ["version_id"]
    )


def downgrade() -> None:
    op.drop_table("proposal_sections")
    op.drop_table("proposal_versions")
    op.drop_table("proposals")
