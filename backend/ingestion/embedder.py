import asyncio
from typing import Any

import structlog
from openai import AsyncOpenAI

log = structlog.get_logger()

_EMBED_BATCH_SIZE: int = 100  # OpenAI recommends <= 2048 inputs, but 100 is safe
_EMBED_DIMENSION: int = 1536   # text-embedding-3-small default


class ChunkEmbedder:
    """Embed code chunks using an OpenAI embeddings model.

    Parameters
    ----------
    openai_client:
        An already-configured :class:`openai.AsyncOpenAI` instance.
    model:
        The embedding model to use.  Defaults to ``text-embedding-3-small``
        which produces 1 536-dimensional vectors at low cost.
    """

    def __init__(
        self,
        openai_client: AsyncOpenAI,
        model: str = "text-embedding-3-small",
    ) -> None:
        self._client = openai_client
        self.model = model

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a single batch of texts (up to *_EMBED_BATCH_SIZE* items)."""
        response = await self._client.embeddings.create(
            model=self.model,
            input=texts,
        )
        # The API returns items in the same order as the input.
        return [item.embedding for item in response.data]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def embed_chunks(self, chunks: list[dict]) -> list[dict]:
        """Add an ``"embedding"`` field to every chunk dict and return the list.

        Chunks are embedded in parallel batches of up to :data:`_EMBED_BATCH_SIZE`
        items each.  The original list is not mutated — a shallow copy with the
        new field is returned.

        Parameters
        ----------
        chunks:
            List of chunk dicts produced by :class:`~ingestion.code_chunker.CodeChunker`.
            Each dict must have a ``"text"`` key.

        Returns
        -------
        list[dict]
            Same dicts with an ``"embedding": list[float]`` field added.
        """
        if not chunks:
            return []

        texts = [c["text"] for c in chunks]

        # Build batches
        batches: list[list[str]] = [
            texts[i : i + _EMBED_BATCH_SIZE]
            for i in range(0, len(texts), _EMBED_BATCH_SIZE)
        ]

        log.info(
            "embedding_chunks",
            total_chunks=len(chunks),
            batches=len(batches),
            model=self.model,
        )

        # Fire all batches in parallel
        batch_results: list[list[list[float]]] = await asyncio.gather(
            *[self._embed_batch(batch) for batch in batches]
        )

        # Flatten batch results into a single ordered list of embeddings
        embeddings: list[list[float]] = [
            vec for batch in batch_results for vec in batch
        ]

        # Pair each chunk with its embedding (shallow copy to stay immutable)
        embedded_chunks: list[dict] = [
            {**chunk, "embedding": embedding}
            for chunk, embedding in zip(chunks, embeddings)
        ]

        log.info(
            "embedding_complete",
            total_chunks=len(embedded_chunks),
            embedding_dim=len(embeddings[0]) if embeddings else 0,
        )
        return embedded_chunks

    async def embed_text(self, text: str) -> list[float]:
        """Return the embedding vector for a single *text* string.

        Intended for query-time use (e.g. similarity search against the
        stored chunk embeddings).
        """
        log.debug("embedding_query_text", char_count=len(text), model=self.model)
        response = await self._client.embeddings.create(
            model=self.model,
            input=[text],
        )
        return response.data[0].embedding
