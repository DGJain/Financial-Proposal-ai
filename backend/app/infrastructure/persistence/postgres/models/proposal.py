"""Proposal aggregate ORM models — the produced document and its edit versions.

One ``proposals`` row (the aggregate root, linked to its generation event) owns an
ordered set of ``proposal_versions``; each version owns an ordered set of
``proposal_sections``. Section order is persisted so the editor can enforce the
structure-lock invariant (ui-design.md Page 3): an edit may change a section's
``body`` but never the headings, ids, or order.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.persistence.postgres.base import Base


class ProposalRow(Base):
    __tablename__ = "proposals"

    proposal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    gen_id: Mapped[str] = mapped_column(String(64), index=True)
    engagement_id: Mapped[str] = mapped_column(String(64), index=True)
    template_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), index=True)

    versions: Mapped[list[ProposalVersionRow]] = relationship(
        back_populates="proposal",
        cascade="all, delete-orphan",
        order_by="ProposalVersionRow.version_no",
    )


class ProposalVersionRow(Base):
    __tablename__ = "proposal_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("proposals.proposal_id"), index=True
    )
    version_no: Mapped[int] = mapped_column(Integer)
    created_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16))

    proposal: Mapped[ProposalRow] = relationship(back_populates="versions")
    sections: Mapped[list[ProposalSectionRow]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="ProposalSectionRow.order",
    )


class ProposalSectionRow(Base):
    __tablename__ = "proposal_sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("proposal_versions.id"), index=True
    )
    section_id: Mapped[str] = mapped_column(String(80))
    slot: Mapped[str] = mapped_column(String(64))
    heading: Mapped[str] = mapped_column(String(256))
    order: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)

    version: Mapped[ProposalVersionRow] = relationship(back_populates="sections")
