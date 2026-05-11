"""Thin wrapper exposing embeddings used by the internal RAG pipeline."""

from src.llm import get_embeddings  # re-export

__all__ = ["get_embeddings"]
