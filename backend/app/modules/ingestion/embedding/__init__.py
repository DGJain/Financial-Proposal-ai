"""Embed + index stage (chunks → ChromaDB repo_financial)."""

from app.modules.ingestion.embedding.indexer import EmbedAndIndex

__all__ = ["EmbedAndIndex"]
