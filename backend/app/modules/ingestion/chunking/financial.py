"""Financial chunking — structure-preserving, tables atomic (document-intelligence
U-3).

The financial repository is the evidence corpus, so its chunking optimizes for
*faithful, citable* fragments rather than uniform token windows:

* every extracted **table is one atomic chunk** — a figure must never be split
  from its row/column context;
* every **figure travels with its caption**;
* flowing prose is packed into bounded text chunks, per page;
* every chunk is **period-tagged** (``fiscal_year``) and carries the issuer/subtype
  so retrieval can filter within the repository.

Emits ``Chunk`` entities (role EVIDENCE) with the document's ACL copied on, ready
to embed. ``vector_id`` is left unset until the index stage assigns it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.chunks.chunk import Chunk, ChunkSpan
from app.domain.documents.acl import AccessControl
from app.domain.ingestion.enums import ContentType
from app.domain.ingestion.extracted import ExtractedDocument
from app.domain.repositories.repository import Repository, RoleInGeneration
from app.modules.ingestion.contracts import RepositoryMetadata

# Soft upper bound (characters) for a packed text chunk before starting a new one.
DEFAULT_MAX_TEXT_CHARS = 1200


@dataclass(frozen=True, slots=True)
class FinancialChunker:
    """Produces atomic, period-tagged financial chunks from an extracted document."""

    embedding_model_version: str
    max_text_chars: int = DEFAULT_MAX_TEXT_CHARS

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
            # 1) Flowing prose → bounded text chunks (kept in reading order).
            for text in self._pack_text(page.text_blocks, self.max_text_chars):
                chunks.append(
                    self._make_chunk(
                        doc_id, ordinal, text, ContentType.TEXT, access, base_md,
                        page_start=page.page_number, page_end=page.page_number,
                    )
                )
                ordinal += 1

            # 2) Each table → one atomic chunk.
            for table in page.tables:
                md = {**base_md, "table_id": table.table_id}
                chunks.append(
                    self._make_chunk(
                        doc_id, ordinal, table.render(), ContentType.TABLE, access, md,
                        page_start=page.page_number, page_end=page.page_number,
                        bbox=table.bbox,
                    )
                )
                ordinal += 1

            # 3) Each figure → caption chunk (figure + caption stay together).
            for figure in page.figures:
                caption = figure.caption or ""
                md = {**base_md, "figure_id": figure.figure_id}
                chunks.append(
                    self._make_chunk(
                        doc_id, ordinal, caption, ContentType.FIGURE, access, md,
                        page_start=page.page_number, page_end=page.page_number,
                        bbox=figure.bbox,
                    )
                )
                ordinal += 1

        return chunks

    @staticmethod
    def _pack_text(blocks: tuple, max_chars: int) -> list[str]:  # type: ignore[type-arg]
        out: list[str] = []
        buffer: list[str] = []
        size = 0
        for block in blocks:
            text = block.text.strip()
            if not text:
                continue
            if size + len(text) > max_chars and buffer:
                out.append("\n".join(buffer))
                buffer, size = [], 0
            buffer.append(text)
            size += len(text) + 1
        if buffer:
            out.append("\n".join(buffer))
        return out

    def _make_chunk(
        self,
        doc_id: str,
        ordinal: int,
        text: str,
        content_type: ContentType,
        access: AccessControl,
        metadata: dict[str, str | int],
        *,
        page_start: int,
        page_end: int,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> Chunk:
        return Chunk(
            chunk_id=f"{doc_id}-c{ordinal:04d}",
            doc_id=doc_id,
            repository=Repository.FINANCIAL,
            role_in_generation=RoleInGeneration.EVIDENCE,
            text=text,
            ordinal=ordinal,
            span=ChunkSpan(page_start=page_start, page_end=page_end, bbox=bbox),
            access=access,
            embedding_model_version=self.embedding_model_version,
            metadata={**metadata, "content_type": content_type.value},
        )
