"""Proposal chunking — section-semantic (document-intelligence U-3).

The exemplar repository is retrieved for *how to say it*, so its chunks preserve
argument flow: text is grouped by proposal **section** (executive summary,
approach, pricing…) into larger narrative windows, and every chunk is tagged with
its ``section_type`` (so retrieval can target the right part of a proposal) and
the proposal ``outcome`` (so won proposals can be weighted up). Chunks carry the
EXEMPLAR role — they are never citable evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.chunks.chunk import Chunk, ChunkSpan
from app.domain.documents.acl import AccessControl
from app.domain.ingestion.enums import ContentType
from app.domain.ingestion.extracted import ExtractedDocument
from app.domain.repositories.repository import Repository, RoleInGeneration
from app.modules.ingestion.contracts import RepositoryMetadata
from app.modules.ingestion.quality.sections import detect_section

# Larger windows than financial — narrative flow over fine-grained citability.
DEFAULT_MAX_SECTION_CHARS = 2400


@dataclass(frozen=True, slots=True)
class _Block:
    text: str
    page: int


@dataclass(frozen=True, slots=True)
class ProposalChunker:
    """Produces section-tagged, narrative-window chunks for a proposal exemplar."""

    embedding_model_version: str
    max_section_chars: int = DEFAULT_MAX_SECTION_CHARS

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
        current_section = "body"

        for section_label, blocks in self._grouped_sections(document):
            current_section = section_label or current_section
            for text, page_start, page_end in self._pack(blocks, self.max_section_chars):
                md: dict[str, str | int] = {
                    **base_md,
                    "section_type": current_section,
                    "content_type": ContentType.TEXT.value,
                }
                chunks.append(
                    Chunk(
                        chunk_id=f"{doc_id}-c{ordinal:04d}",
                        doc_id=doc_id,
                        repository=Repository.PROPOSAL,
                        role_in_generation=RoleInGeneration.EXEMPLAR,
                        text=text,
                        ordinal=ordinal,
                        span=ChunkSpan(page_start=page_start, page_end=page_end),
                        access=access,
                        embedding_model_version=self.embedding_model_version,
                        metadata=md,
                    )
                )
                ordinal += 1
        return chunks

    def _grouped_sections(
        self, document: ExtractedDocument
    ) -> list[tuple[str | None, list[_Block]]]:
        """Walk blocks in reading order, starting a new group at each section cue."""
        groups: list[tuple[str | None, list[_Block]]] = []
        current_label: str | None = None
        current: list[_Block] = []
        for page in document.pages:
            for block in page.text_blocks:
                if not block.text.strip():
                    continue
                section = detect_section(block.text)
                if section is not None and current:
                    groups.append((current_label, current))
                    current = []
                if section is not None:
                    current_label = section.value
                current.append(_Block(text=block.text.strip(), page=page.page_number))
        if current:
            groups.append((current_label, current))
        return groups

    def _pack(self, blocks: list[_Block], max_chars: int) -> list[tuple[str, int, int]]:
        out: list[tuple[str, int, int]] = []
        buffer: list[str] = []
        size = 0
        page_lo = page_hi = blocks[0].page if blocks else 1
        for block in blocks:
            if size + len(block.text) > max_chars and buffer:
                out.append(("\n".join(buffer), page_lo, page_hi))
                buffer, size = [], 0
                page_lo = page_hi = block.page
            if not buffer:
                page_lo = block.page
            page_hi = block.page
            buffer.append(block.text)
            size += len(block.text) + 1
        if buffer:
            out.append(("\n".join(buffer), page_lo, page_hi))
        return out
