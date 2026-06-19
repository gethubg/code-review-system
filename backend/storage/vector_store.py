from __future__ import annotations

import os
from typing import Any, Optional

import structlog
from openai import AsyncOpenAI
from pinecone import Pinecone, ServerlessSpec

logger = structlog.get_logger(__name__)

_EMBEDDING_MODEL = "text-embedding-3-small"
_EMBEDDING_DIMENSIONS = 1536
_DEFAULT_TOP_K = 10


class PineconeStore:
    """Async-friendly Pinecone vector store wrapper for code-review chunks."""

    def __init__(
        self,
        index_name: Optional[str] = None,
        pinecone_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None,
        cloud: str = "aws",
        region: str = "us-east-1",
    ) -> None:
        self._index_name = index_name or os.environ.get(
            "PINECONE_INDEX_NAME", "code-review"
        )
        self._pinecone_api_key = pinecone_api_key or os.environ.get(
            "PINECONE_API_KEY", ""
        )
        self._cloud = cloud
        self._region = region

        openai_key = openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        self._openai = AsyncOpenAI(api_key=openai_key)

        self._pc: Optional[Pinecone] = None
        self._index = None

    async def init(self) -> None:
        """Initialise Pinecone client and ensure the index exists."""
        if not self._pinecone_api_key:
            raise ValueError(
                "Pinecone API key is required. Set PINECONE_API_KEY env var."
            )

        self._pc = Pinecone(api_key=self._pinecone_api_key)

        existing = [idx.name for idx in self._pc.list_indexes()]
        if self._index_name not in existing:
            logger.info(
                "pinecone_creating_index",
                index_name=self._index_name,
                dimensions=_EMBEDDING_DIMENSIONS,
            )
            self._pc.create_index(
                name=self._index_name,
                dimension=_EMBEDDING_DIMENSIONS,
                metric="cosine",
                spec=ServerlessSpec(cloud=self._cloud, region=self._region),
            )

        self._index = self._pc.Index(self._index_name)
        logger.info("pinecone_initialized", index_name=self._index_name)

    def _require_index(self) -> None:
        if self._index is None:
            raise RuntimeError(
                "PineconeStore has not been initialised. Call await store.init() first."
            )

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts with the OpenAI embedding model."""
        response = await self._openai.embeddings.create(
            input=texts,
            model=_EMBEDDING_MODEL,
            dimensions=_EMBEDDING_DIMENSIONS,
        )
        return [item.embedding for item in response.data]

    async def upsert_chunks(
        self,
        run_id: str,
        chunks: list[dict[str, Any]],
        batch_size: int = 100,
    ) -> None:
        """Embed chunks and upsert into Pinecone.

        Each chunk must have at minimum a ``text`` key. All other keys are
        stored as metadata. A ``run_id`` key is injected automatically so
        chunks can be scoped per review run.

        Args:
            run_id: Identifier of the review run these chunks belong to.
            chunks: List of dicts, each containing at least ``{"text": "..."}``.
            batch_size: Number of vectors to upsert per Pinecone request.
        """
        self._require_index()

        if not chunks:
            logger.debug("upsert_chunks_empty", run_id=run_id)
            return

        texts = [c["text"] for c in chunks]
        logger.info("embedding_chunks", run_id=run_id, count=len(texts))

        embeddings = await self._embed(texts)

        vectors: list[dict[str, Any]] = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            vector_id = f"{run_id}_{idx}"
            metadata: dict[str, Any] = {
                k: v
                for k, v in chunk.items()
                if k != "text" and isinstance(v, (str, int, float, bool, list))
            }
            metadata["run_id"] = run_id
            metadata["text"] = chunk["text"]
            vectors.append(
                {
                    "id": vector_id,
                    "values": embedding,
                    "metadata": metadata,
                }
            )

        for start in range(0, len(vectors), batch_size):
            batch = vectors[start : start + batch_size]
            self._index.upsert(vectors=batch)
            logger.debug(
                "pinecone_upserted_batch",
                run_id=run_id,
                batch_start=start,
                batch_size=len(batch),
            )

        logger.info("upsert_chunks_complete", run_id=run_id, total=len(vectors))

    async def query_similar(
        self,
        run_id: str,
        query_text: str,
        top_k: int = _DEFAULT_TOP_K,
    ) -> list[dict[str, Any]]:
        """Return the top-k most similar chunks for a given query text.

        Results are filtered to the specified run_id so different review
        runs do not bleed into each other.

        Args:
            run_id: Scope the search to this review run.
            query_text: Natural-language query to embed and search.
            top_k: Maximum number of results to return.

        Returns:
            List of dicts with keys ``id``, ``score``, and all metadata fields.
        """
        self._require_index()

        logger.debug("query_similar", run_id=run_id, top_k=top_k)
        query_embedding = (await self._embed([query_text]))[0]

        response = self._index.query(
            vector=query_embedding,
            top_k=top_k,
            filter={"run_id": {"$eq": run_id}},
            include_metadata=True,
        )

        results: list[dict[str, Any]] = []
        for match in response.matches:
            entry: dict[str, Any] = {"id": match.id, "score": match.score}
            if match.metadata:
                entry.update(match.metadata)
            results.append(entry)

        logger.info(
            "query_similar_complete",
            run_id=run_id,
            returned=len(results),
        )
        return results

    async def delete_run_chunks(self, run_id: str) -> None:
        """Delete all vectors associated with a specific review run.

        Uses Pinecone's metadata-filter delete when available; falls back to
        listing and deleting by ID prefix for indexes that do not support it.

        Args:
            run_id: The review run whose vectors should be removed.
        """
        self._require_index()

        logger.info("delete_run_chunks_start", run_id=run_id)

        try:
            # Preferred path: delete by metadata filter (requires Pinecone paid tier
            # or indexes with filter-delete support).
            self._index.delete(filter={"run_id": {"$eq": run_id}})
            logger.info("delete_run_chunks_complete_filter", run_id=run_id)
        except Exception as filter_exc:
            # Fallback: enumerate IDs by prefix and delete in batches.
            logger.warning(
                "delete_by_filter_failed_falling_back",
                run_id=run_id,
                error=str(filter_exc),
            )
            try:
                # list() returns paginated ID results; prefix match on run_id
                ids_to_delete: list[str] = []
                for id_batch in self._index.list(prefix=f"{run_id}_"):
                    ids_to_delete.extend(id_batch)

                if ids_to_delete:
                    batch_size = 1000
                    for start in range(0, len(ids_to_delete), batch_size):
                        batch = ids_to_delete[start : start + batch_size]
                        self._index.delete(ids=batch)
                    logger.info(
                        "delete_run_chunks_complete_prefix",
                        run_id=run_id,
                        deleted=len(ids_to_delete),
                    )
                else:
                    logger.info(
                        "delete_run_chunks_nothing_found",
                        run_id=run_id,
                    )
            except Exception as fallback_exc:
                logger.error(
                    "delete_run_chunks_failed",
                    run_id=run_id,
                    error=str(fallback_exc),
                )
                raise RuntimeError(
                    f"Failed to delete vectors for run {run_id}: {fallback_exc}"
                ) from fallback_exc
