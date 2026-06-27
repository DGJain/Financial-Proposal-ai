"""Template chunking — structure/placeholder-aware (document-intelligence U-3).

A template chunk is a **reusable unit**: a structural block (a section skeleton)
kept intact with its placeholder slots preserved **verbatim**, so the template
stays parameterizable after retrieval. Each non-empty block becomes its own chunk
(independently retrievable), tables stay atomic, and every chunk records its slot
count. Chunks carry the SCAFFOLD role.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.chunks.chunk import Chunk, ChunkSpan
from app.domain.documents.acl import AccessControl
from app.domain.ingestion.enums import ContentType
from app.domain.ingestion.extracted import ExtractedDocument
from app.domain.repositories.repository import Repository, RoleInGeneration
from app.modules.ingestion.contracts import RepositoryMetadata
from app.modules.ingestion.quality.placeholders import find_slots


@dataclass(frozen=True, slots=True)
class TemplateChunker:
    """Produces placeholder-preserving, structurally atomic template chunks."""

    embedding_model_version: str

    def chunk(
        self,
        document: ExtractedDocument,
        *,
        doc_id: str,
        access: AccessControl,
        metadata: RepositoryMetadata,
    ) -> list[Chunk]:
        base_md = metadata.chunk_metadata()
        chunks: list[Chunk] = []
        ordinal = 0

        for page in document.pages:
            # Each structural text block → one reusable unit (verbatim, slots intact).
            for block in page.text_blocks:
                text = block.text.rstrip()
                if not text:
                    continue
                slots = find_slots(text)
                md: dict[str, str | int] = {
                    **base_md,
                    "content_type": ContentType.TEXT.value,
                    "slot_count": len(slots),
                }
                chunks.append(
                    self._make_chunk(
                        doc_id, ordinal, text, access, md, page.page_number, bbox=block.bbox
                    )
                )
                ordinal += 1

            # Tables stay atomic (a pricing grid is one reusable unit).
            for table in page.tables:
                md = {**base_md, "content_type": ContentType.TABLE.value, "table_id": table.table_id}
                chunks.append(
                    self._make_chunk(
                        doc_id, ordinal, table.render(), access, md, page.page_number,
                        bbox=table.bbox,
                    )
                )
                ordinal += 1
        return chunks

    def _make_chunk(
        self,
        doc_id: str,
        ordinal: int,
        text: str,
        access: AccessControl,
        metadata: dict[str, str | int],
        page: int,
        *,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> Chunk:
        return Chunk(
            chunk_id=f"{doc_id}-c{ordinal:04d}",
            doc_id=doc_id,
            repository=Repository.TEMPLATE,
            role_in_generation=RoleInGeneration.SCAFFOLD,
            text=text,
            ordinal=ordinal,
            span=ChunkSpan(page_start=page, page_end=page, bbox=bbox),
            access=access,
            embedding_model_version=self.embedding_model_version,
            metadata=metadata,
        )
