"""Hybrid search combining BM25 and semantic search."""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..logging.structured import get_logger
from .collections import CollectionManager, ContentType, Document
from .vector_store import VectorStore

logger = get_logger(__name__)


@dataclass
class HybridSearchResult:
    """Hybrid search result combining BM25 and semantic scores."""

    content_id: str
    content_type: str
    bm25_score: float
    semantic_score: float
    hybrid_score: float
    metadata: Dict[str, Any]
    text_snippet: Optional[str] = None


class TextIndex:
    """In-memory text index for BM25 search."""

    def __init__(self) -> None:
        """Initialize text index."""
        self.documents: Dict[str, Document] = {}
        self.tokenized_corpus: List[List[str]] = []
        self.doc_ids: List[str] = []
        self.bm25: Optional[BM25Okapi] = None

    def add_documents(self, documents: List[Document]) -> None:
        """Add documents to the index.

        Args:
            documents: List of documents to index
        """
        for doc in documents:
            doc_id = str(doc.content_id)
            self.documents[doc_id] = doc

            # Tokenize document
            tokens = self._tokenize(doc.to_searchable_text())
            self.tokenized_corpus.append(tokens)
            self.doc_ids.append(doc_id)

        # Rebuild BM25 index
        self._rebuild_bm25()

    def _tokenize(self, text_input: str) -> List[str]:
        """Simple tokenization for BM25.

        Args:
            text_input: Text to tokenize

        Returns:
            List of tokens
        """
        # Convert to lowercase and split
        tokens = text_input.lower().split()

        # Remove punctuation and filter short tokens
        cleaned_tokens = []
        for token in tokens:
            # Remove common punctuation
            cleaned = token.strip(".,!?;:\"'()[]{}|\\/<>@#$%^&*+=~`")
            if len(cleaned) > 2:  # Filter very short tokens
                cleaned_tokens.append(cleaned)

        return cleaned_tokens

    def _rebuild_bm25(self) -> None:
        """Rebuild BM25 index."""
        if self.tokenized_corpus:
            self.bm25 = BM25Okapi(self.tokenized_corpus)
            logger.info(f"Rebuilt BM25 index with {len(self.tokenized_corpus)} documents")

    def search(self, query: str, top_k: int = 100) -> List[Tuple[str, float]]:
        """Search using BM25.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of (doc_id, score) tuples
        """
        if not self.bm25:
            return []

        # Tokenize query
        query_tokens = self._tokenize(query)

        # Get BM25 scores
        scores = self.bm25.get_scores(query_tokens)

        # Get top-k results
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append((self.doc_ids[idx], float(scores[idx])))

        return results

    def get_document(self, doc_id: str) -> Optional[Document]:
        """Get document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document or None
        """
        return self.documents.get(doc_id)

    def clear(self) -> None:
        """Clear the index."""
        self.documents.clear()
        self.tokenized_corpus.clear()
        self.doc_ids.clear()
        self.bm25 = None


class HybridSearch:
    """Hybrid search combining BM25 and semantic search."""

    def __init__(
        self,
        vector_store: VectorStore,
        collection_manager: CollectionManager,
        session: Union[Session, AsyncSession],
        alpha: float = 0.5,
    ):
        """Initialize hybrid search.

        Args:
            vector_store: Vector store instance
            collection_manager: Collection manager instance
            session: Database session
            alpha: Weight for semantic search (0-1), BM25 weight is (1-alpha)
        """
        self.vector_store = vector_store
        self.collection_manager = collection_manager
        self.session = session
        self.alpha = alpha

        # Text indices for each collection
        self._text_indices: Dict[str, TextIndex] = defaultdict(TextIndex)

    async def index_documents(
        self,
        documents: List[Document],
        collection_name: str,
    ) -> None:
        """Index documents for hybrid search.

        Args:
            documents: Documents to index
            collection_name: Target collection
        """
        # Add to text index
        self._text_indices[collection_name].add_documents(documents)

        # Add to vector store
        await self.collection_manager.add_documents(
            documents,
            collection_name=collection_name,
        )

    async def search(
        self,
        query: str,
        collection_name: str,
        limit: int = 10,
        content_type: Optional[ContentType] = None,
        filters: Optional[Dict[str, Any]] = None,
        alpha: Optional[float] = None,
        return_text: bool = True,
        snippet_length: int = 200,
    ) -> List[HybridSearchResult]:
        """Perform hybrid search.

        Args:
            query: Search query
            collection_name: Collection to search
            limit: Maximum results
            content_type: Filter by content type
            filters: Additional filters
            alpha: Override default alpha (semantic weight)
            return_text: Whether to return text snippets
            snippet_length: Maximum snippet length

        Returns:
            List of hybrid search results
        """
        alpha = alpha if alpha is not None else self.alpha

        # Perform BM25 search
        text_index = self._text_indices[collection_name]
        bm25_results = text_index.search(query, top_k=limit * 3)  # Get more for reranking

        # Perform semantic search
        semantic_results = await self.collection_manager.search_similar(
            query=query,
            collection_name=collection_name,
            limit=limit * 3,
            content_type=content_type,
            filters=filters,
        )

        # Combine and rerank results
        hybrid_results = self._combine_results(
            bm25_results=bm25_results,
            semantic_results=semantic_results,
            alpha=alpha,
            text_index=text_index,
            return_text=return_text,
            snippet_length=snippet_length,
            query=query,
        )

        # Sort by hybrid score and limit
        hybrid_results.sort(key=lambda x: x.hybrid_score, reverse=True)

        return hybrid_results[:limit]

    def _combine_results(
        self,
        bm25_results: List[Tuple[str, float]],
        semantic_results: List[Dict[str, Any]],
        alpha: float,
        text_index: TextIndex,
        return_text: bool,
        snippet_length: int,
        query: str,
    ) -> List[HybridSearchResult]:
        """Combine BM25 and semantic results.

        Args:
            bm25_results: BM25 search results
            semantic_results: Semantic search results
            alpha: Semantic weight
            text_index: Text index for document lookup
            return_text: Whether to extract text snippets
            snippet_length: Maximum snippet length
            query: Original query for snippet extraction

        Returns:
            Combined results
        """
        # Normalize scores
        bm25_scores = self._normalize_scores({doc_id: score for doc_id, score in bm25_results})

        semantic_scores = self._normalize_scores(
            {result["content_id"]: result["score"] for result in semantic_results}
        )

        # Get all unique document IDs
        all_doc_ids = set(bm25_scores.keys()) | set(semantic_scores.keys())

        # Combine scores
        hybrid_results = []

        for doc_id in all_doc_ids:
            # Get scores (default to 0 if not found)
            bm25_score = bm25_scores.get(doc_id, 0.0)
            semantic_score = semantic_scores.get(doc_id, 0.0)

            # Calculate hybrid score
            hybrid_score = alpha * semantic_score + (1 - alpha) * bm25_score

            # Get document metadata
            doc = text_index.get_document(doc_id)

            # Find in semantic results for metadata
            metadata = {}
            content_type = "unknown"

            for result in semantic_results:
                if result["content_id"] == doc_id:
                    metadata = result.get("metadata", {})
                    content_type = result.get("content_type", "unknown")
                    break

            # Extract text snippet if requested
            text_snippet = None
            if return_text and doc:
                text_snippet = self._extract_snippet(
                    doc.to_searchable_text(),
                    query,
                    snippet_length,
                )

            hybrid_results.append(
                HybridSearchResult(
                    content_id=doc_id,
                    content_type=content_type,
                    bm25_score=bm25_score,
                    semantic_score=semantic_score,
                    hybrid_score=hybrid_score,
                    metadata=metadata,
                    text_snippet=text_snippet,
                )
            )

        return hybrid_results

    def _normalize_scores(self, scores: Dict[str, float]) -> Dict[str, float]:
        """Normalize scores to [0, 1] range.

        Args:
            scores: Dictionary of doc_id -> score

        Returns:
            Normalized scores
        """
        if not scores:
            return {}

        # Get min and max scores
        min_score = min(scores.values())
        max_score = max(scores.values())

        # Avoid division by zero
        if max_score == min_score:
            return {doc_id: 1.0 for doc_id in scores}

        # Normalize
        normalized = {}
        for doc_id, score in scores.items():
            normalized[doc_id] = (score - min_score) / (max_score - min_score)

        return normalized

    def _extract_snippet(
        self,
        text_content: str,
        query: str,
        max_length: int,
    ) -> str:
        """Extract relevant snippet from text.

        Args:
            text_content: Full text
            query: Search query
            max_length: Maximum snippet length

        Returns:
            Text snippet
        """
        # Simple approach: find query terms and extract surrounding context
        query_terms = query.lower().split()
        text_lower = text_content.lower()

        # Find best position
        best_pos = 0
        best_score = 0

        for i in range(len(text_content) - max_length):
            snippet = text_lower[i : i + max_length]
            score = sum(1 for term in query_terms if term in snippet)

            if score > best_score:
                best_score = score
                best_pos = i

        # Extract snippet
        snippet = text_content[best_pos : best_pos + max_length]

        # Clean up edges
        if best_pos > 0:
            snippet = "..." + snippet
        if best_pos + max_length < len(text_content):
            snippet = snippet + "..."

        return snippet

    async def find_similar_with_keywords(
        self,
        query: str,
        keywords: List[str],
        collection_name: str,
        limit: int = 10,
        keyword_boost: float = 2.0,
    ) -> List[HybridSearchResult]:
        """Search with additional keyword boosting.

        Args:
            query: Main search query
            keywords: Important keywords to boost
            collection_name: Collection to search
            limit: Maximum results
            keyword_boost: Boost factor for documents containing keywords

        Returns:
            Search results
        """
        # Perform regular hybrid search
        results = await self.search(
            query=query,
            collection_name=collection_name,
            limit=limit * 2,  # Get more for reranking
        )

        # Boost results containing keywords
        for result in results:
            doc = self._text_indices[collection_name].get_document(result.content_id)
            if doc:
                doc_text = doc.to_searchable_text().lower()
                keyword_count = sum(1 for kw in keywords if kw.lower() in doc_text)

                if keyword_count > 0:
                    # Apply boost
                    boost_factor = 1 + (keyword_boost - 1) * (keyword_count / len(keywords))
                    result.hybrid_score *= boost_factor

        # Resort and limit
        results.sort(key=lambda x: x.hybrid_score, reverse=True)

        return results[:limit]

    async def search_multiple_collections(
        self,
        query: str,
        collection_names: List[str],
        limit_per_collection: int = 5,
        global_limit: int = 20,
    ) -> List[HybridSearchResult]:
        """Search across multiple collections.

        Args:
            query: Search query
            collection_names: Collections to search
            limit_per_collection: Max results per collection
            global_limit: Total max results

        Returns:
            Combined search results
        """
        all_results = []

        # Search each collection
        for collection_name in collection_names:
            try:
                results = await self.search(
                    query=query,
                    collection_name=collection_name,
                    limit=limit_per_collection,
                )

                # Add collection name to metadata
                for result in results:
                    result.metadata["collection"] = collection_name

                all_results.extend(results)

            except Exception as e:
                logger.error(f"Error searching collection {collection_name}: {e}")

        # Sort by hybrid score and limit
        all_results.sort(key=lambda x: x.hybrid_score, reverse=True)

        return all_results[:global_limit]

    def update_alpha(self, alpha: float) -> None:
        """Update the alpha parameter for hybrid scoring.

        Args:
            alpha: New alpha value (0-1)
        """
        if not 0 <= alpha <= 1:
            raise ValueError("Alpha must be between 0 and 1")

        self.alpha = alpha
        logger.info(f"Updated hybrid search alpha to {alpha}")

    def clear_text_index(self, collection_name: Optional[str] = None) -> None:
        """Clear text indices.

        Args:
            collection_name: Specific collection to clear, or None for all
        """
        if collection_name:
            self._text_indices[collection_name].clear()
            logger.info(f"Cleared text index for collection {collection_name}")
        else:
            for name in list(self._text_indices.keys()):
                self._text_indices[name].clear()
            self._text_indices.clear()
            logger.info("Cleared all text indices")

    async def get_search_stats(self) -> Dict[str, Any]:
        """Get search statistics.

        Returns:
            Search statistics
        """
        stats: Dict[str, Any] = {
            "alpha": self.alpha,
            "text_indices": {},
            "vector_collections": {},
        }

        # Text index stats
        for name, index in self._text_indices.items():
            stats["text_indices"][name] = {
                "document_count": len(index.documents),
                "has_bm25": index.bm25 is not None,
            }

        # Vector collection stats
        for name in self._text_indices.keys():
            try:
                collection_stats = await self.vector_store.get_collection_stats(name)
                stats["vector_collections"][name] = collection_stats
            except Exception as e:
                logger.error(f"Error getting stats for collection {name}: {e}")

        return stats
