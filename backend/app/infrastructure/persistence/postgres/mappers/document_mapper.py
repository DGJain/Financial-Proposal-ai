"""Translation between the ``Document`` domain entity and ``DocumentRow``.

Isolating mapping here keeps the domain free of ORM concerns and the ORM free of
domain logic (Clean Architecture). Enums are stored as their string values and
reconstructed on read.
"""

from __future__ import annotations

from app.domain.documents.acl import AccessControl
from app.domain.documents.document import Document, Provenance
from app.domain.documents.enums import FileType, SensitivityFlag
from app.domain.repositories.repository import Repository, SoftDistribution
from app.infrastructure.persistence.postgres.models.document import DocumentRow


def to_row(document: Document) -> DocumentRow:
    """Build a new ORM row from a domain document."""
    prov = document.provenance
    access = document.access
    pi = document.soft_distribution
    return DocumentRow(
        doc_id=document.doc_id,
        repository=document.repository.value,
        subtype=document.subtype,
        pi_financial=pi.financial,
        pi_proposal=pi.proposal,
        pi_template=pi.template,
        repo_confidence=document.repo_confidence,
        source_uri=prov.source_uri,
        file_type=prov.file_type.value,
        ingestion_ts=prov.ingestion_ts,
        page_count=prov.page_count,
        language=prov.language,
        content_hash=prov.content_hash,
        acl_groups=sorted(access.acl_groups),
        engagement_id=access.engagement_id,
        classification=access.classification,
        sensitivity=sorted(flag.value for flag in document.sensitivity),
        object_uri_versioned=document.object_uri_versioned,
        lineage_root=document.lineage_root,
        parent_doc_id=document.parent_doc_id,
        version=document.version,
    )


def to_domain(row: DocumentRow) -> Document:
    """Reconstruct a domain document from an ORM row."""
    return Document(
        doc_id=row.doc_id,
        repository=Repository(row.repository),
        subtype=row.subtype,
        provenance=Provenance(
            source_uri=row.source_uri,
            file_type=FileType(row.file_type),
            ingestion_ts=row.ingestion_ts,
            page_count=row.page_count,
            language=row.language,
            content_hash=row.content_hash,
        ),
        access=AccessControl(
            acl_groups=frozenset(row.acl_groups),
            engagement_id=row.engagement_id,
            classification=row.classification,
        ),
        soft_distribution=SoftDistribution(
            financial=row.pi_financial,
            proposal=row.pi_proposal,
            template=row.pi_template,
        ),
        repo_confidence=row.repo_confidence,
        sensitivity=frozenset(SensitivityFlag(s) for s in row.sensitivity),
        object_uri_versioned=row.object_uri_versioned,
        lineage_root=row.lineage_root,
        parent_doc_id=row.parent_doc_id,
        version=row.version,
    )
