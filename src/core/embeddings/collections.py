"""Collection management for different content types."""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ..logging.structured import get_logger
from .models import ModelType
from .vector_store import Collection, VectorStore

if TYPE_CHECKING:
    from .generator import EmbeddingGenerator

logger = get_logger(__name__)


class ContentType(str, Enum):
    """Supported content types."""

    PAPER = "paper"
    EVIDENCE = "evidence"
    CLAIM = "claim"
    SECTION = "section"
    PARAGRAPH = "paragraph"
    ABSTRACT = "abstract"


@dataclass
class Document:
    """Document representation for embedding."""

    content_id: Union[str, UUID]
    content_type: ContentType
    text: str
    metadata: Dict[str, Any]

    def to_searchable_text(self) -> str:
        """Convert document to searchable text.

        Returns:
            Text optimized for search
        """
        parts = [self.text]

        # Add metadata fields that should be searchable
        if "title" in self.metadata:
            parts.insert(0, f"Title: {self.metadata['title']}")

        if "authors" in self.metadata and isinstance(self.metadata["authors"], list):
            authors = ", ".join(self.metadata["authors"])
            parts.append(f"Authors: {authors}")

        if "keywords" in self.metadata and isinstance(self.metadata["keywords"], list):
            keywords = ", ".join(self.metadata["keywords"])
            parts.append(f"Keywords: {keywords}")

        if "journal" in self.metadata:
            parts.append(f"Journal: {self.metadata['journal']}")

        return "\n\n".join(parts)


class CollectionManager:
    """Manages vector collections for different content types."""

    def __init__(
        self,
        vector_store: VectorStore,
        embedding_generator: "EmbeddingGenerator",
        session: Union[Session, AsyncSession],
    ):
        """Initialize collection manager.

        Args:
            vector_store: Vector store instance
            embedding_generator: Embedding generator instance
            session: Database session
        """
        self.vector_store = vector_store
        self.embedding_generator = embedding_generator
        self.session = session

        # Initialize collections
        self._init_collections()

    def _init_collections(self) -> None:
        """Initialize predefined collections."""
        # Papers collection - full documents
        self.vector_store.register_collection(
            Collection(
                name="papers",
                dimensions=768,  # Using all-mpnet-base-v2
                distance_metric="cosine",
                index_type="ivfflat",
                index_params={"lists": 100},
            )
        )

        # Evidence collection - specific evidence snippets
        self.vector_store.register_collection(
            Collection(
                name="evidence",
                dimensions=384,  # Using all-MiniLM-L12-v2
                distance_metric="cosine",
                index_type="ivfflat",
                index_params={"lists": 50},
            )
        )

        # Claims collection - research claims
        self.vector_store.register_collection(
            Collection(
                name="claims",
                dimensions=384,  # Using all-MiniLM-L12-v2
                distance_metric="cosine",
                index_type="ivfflat",
                index_params={"lists": 50},
            )
        )

        # Sections collection - paper sections
        self.vector_store.register_collection(
            Collection(
                name="sections",
                dimensions=384,  # Using all-MiniLM-L6-v2 for faster search
                distance_metric="cosine",
                index_type="hnsw",
                index_params={"m": 16, "ef_construction": 200},
            )
        )

        logger.info("Initialized vector collections")

    async def add_documents(
        self,
        documents: List[Document],
        collection_name: str,
        model_name: Optional[str] = None,
        batch_size: int = 32,
        show_progress: bool = False,
    ) -> List[str]:
        """Add documents to a collection.

        Args:
            documents: List of documents to add
            collection_name: Target collection name
            model_name: Optional specific model to use
            batch_size: Batch size for embedding
            show_progress: Show progress bar

        Returns:
            List of embedding IDs
        """
        if not documents:
            return []

        # Select appropriate model based on collection
        if model_name is None:
            model_name = self._select_model_for_collection(collection_name)

        # Extract texts and metadata
        texts = [doc.to_searchable_text() for doc in documents]
        content_ids = [doc.content_id for doc in documents]
        content_types = [doc.content_type.value for doc in documents]
        metadata_list = [doc.metadata for doc in documents]

        # Generate embeddings
        embeddings = self.embedding_generator.embed_texts(
            texts,
            model_name=model_name,
            batch_size=batch_size,
            show_progress=show_progress,
            use_cache=True,
        )

        # Store in vector database
        # embed_texts always returns List[List[float]] for list input
        embedding_ids = await self.vector_store.add_embeddings(
            collection=collection_name,
            embeddings=embeddings,  # type: ignore[arg-type]
            content_ids=content_ids,
            content_types=content_types,
            model_name=model_name,
            metadata_list=metadata_list,
        )

        logger.info(
            f"Added {len(documents)} documents to collection '{collection_name}' "
            f"using model {model_name}"
        )

        return embedding_ids

    async def search_similar(
        self,
        query: str,
        collection_name: str,
        limit: int = 10,
        content_type: Optional[ContentType] = None,
        filters: Optional[Dict[str, Any]] = None,
        threshold: Optional[float] = None,
        model_name: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Search for similar documents.

        Args:
            query: Search query
            collection_name: Collection to search
            limit: Maximum results
            content_type: Filter by content type
            filters: Additional metadata filters
            threshold: Similarity threshold
            model_name: Optional specific model for query embedding

        Returns:
            List of search results with metadata
        """
        # Select appropriate model
        if model_name is None:
            model_name = self._select_model_for_collection(collection_name)

        # Generate query embedding
        query_embedding = self.embedding_generator.embed_texts(
            query,
            model_name=model_name,
            model_type=ModelType.QUERY,
        )

        # Build filters
        search_filters = filters or {}
        if content_type:
            search_filters["content_type"] = content_type.value

        # Search
        # embed_texts returns List[float] for single string input
        results = await self.vector_store.search(
            collection=collection_name,
            query_embedding=query_embedding,  # type: ignore[arg-type]
            limit=limit,
            filters=search_filters,
            threshold=threshold,
        )

        # Enrich results
        enriched_results = []
        for result in results:
            enriched_result = {
                "content_id": result.content_id,
                "content_type": result.content_type,
                "score": result.score,
                "metadata": result.metadata,
            }

            # Add collection-specific fields
            if collection_name == "papers" and "title" in result.metadata:
                enriched_result["title"] = result.metadata["title"]
                enriched_result["authors"] = result.metadata.get("authors", [])
                enriched_result["year"] = result.metadata.get("year")

            enriched_results.append(enriched_result)

        return enriched_results

    async def add_paper(
        self,
        paper_id: Union[str, UUID],
        title: str,
        abstract: str,
        full_text: Optional[str] = None,
        authors: Optional[List[str]] = None,
        journal: Optional[str] = None,
        year: Optional[int] = None,
        doi: Optional[str] = None,
        keywords: Optional[List[str]] = None,
        sections: Optional[Dict[str, str]] = None,
    ) -> Dict[str, List[str]]:
        """Add a paper with its components to appropriate collections.

        Args:
            paper_id: Paper identifier
            title: Paper title
            abstract: Paper abstract
            full_text: Full paper text
            authors: List of authors
            journal: Journal name
            year: Publication year
            doi: Digital Object Identifier
            keywords: List of keywords
            sections: Dictionary of section_name -> section_text

        Returns:
            Dictionary mapping collection names to embedding IDs
        """
        embedding_ids = {}

        # Common metadata
        base_metadata = {
            "paper_id": str(paper_id),
            "title": title,
            "authors": authors or [],
            "journal": journal,
            "year": year,
            "doi": doi,
            "keywords": keywords or [],
        }

        # Add full paper to papers collection
        if full_text:
            paper_doc = Document(
                content_id=paper_id,
                content_type=ContentType.PAPER,
                text=full_text,
                metadata=base_metadata,
            )
            paper_ids = await self.add_documents(
                [paper_doc],
                collection_name="papers",
            )
            embedding_ids["papers"] = paper_ids

        # Add abstract separately for faster search
        abstract_doc = Document(
            content_id=paper_id,
            content_type=ContentType.ABSTRACT,
            text=abstract,
            metadata={**base_metadata, "section": "abstract"},
        )
        abstract_ids = await self.add_documents(
            [abstract_doc],
            collection_name="sections",
        )
        embedding_ids["abstract"] = abstract_ids

        # Add individual sections
        if sections:
            section_docs = []
            for section_name, section_text in sections.items():
                section_doc = Document(
                    content_id=paper_id,
                    content_type=ContentType.SECTION,
                    text=section_text,
                    metadata={**base_metadata, "section": section_name},
                )
                section_docs.append(section_doc)

            if section_docs:
                section_ids = await self.add_documents(
                    section_docs,
                    collection_name="sections",
                    batch_size=16,
                )
                embedding_ids["sections"] = section_ids

        logger.info(f"Added paper {paper_id} to vector collections")
        return embedding_ids

    async def add_evidence(
        self,
        evidence_id: Union[str, UUID],
        text: str,
        paper_id: Union[str, UUID],
        claim_ids: Optional[List[Union[str, UUID]]] = None,
        location: Optional[Dict[str, Any]] = None,
        evidence_type: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> List[str]:
        """Add evidence to the evidence collection.

        Args:
            evidence_id: Evidence identifier
            text: Evidence text
            paper_id: Source paper ID
            claim_ids: Related claim IDs
            location: Location in paper (page, section, etc.)
            evidence_type: Type of evidence
            confidence: Confidence score

        Returns:
            List of embedding IDs
        """
        metadata = {
            "paper_id": str(paper_id),
            "claim_ids": [str(cid) for cid in (claim_ids or [])],
            "location": location or {},
            "evidence_type": evidence_type,
            "confidence": confidence,
        }

        evidence_doc = Document(
            content_id=evidence_id,
            content_type=ContentType.EVIDENCE,
            text=text,
            metadata=metadata,
        )

        return await self.add_documents(
            [evidence_doc],
            collection_name="evidence",
        )

    async def add_claim(
        self,
        claim_id: Union[str, UUID],
        claim_text: str,
        evidence_ids: Optional[List[Union[str, UUID]]] = None,
        paper_ids: Optional[List[Union[str, UUID]]] = None,
        claim_type: Optional[str] = None,
        confidence: Optional[float] = None,
        tags: Optional[List[str]] = None,
    ) -> List[str]:
        """Add a claim to the claims collection.

        Args:
            claim_id: Claim identifier
            claim_text: Claim text
            evidence_ids: Supporting evidence IDs
            paper_ids: Related paper IDs
            claim_type: Type of claim
            confidence: Confidence score
            tags: Claim tags

        Returns:
            List of embedding IDs
        """
        metadata = {
            "evidence_ids": [str(eid) for eid in (evidence_ids or [])],
            "paper_ids": [str(pid) for pid in (paper_ids or [])],
            "claim_type": claim_type,
            "confidence": confidence,
            "tags": tags or [],
        }

        claim_doc = Document(
            content_id=claim_id,
            content_type=ContentType.CLAIM,
            text=claim_text,
            metadata=metadata,
        )

        return await self.add_documents(
            [claim_doc],
            collection_name="claims",
        )

    async def find_related_evidence(
        self,
        claim_text: str,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Find evidence related to a claim.

        Args:
            claim_text: Claim to find evidence for
            limit: Maximum results
            threshold: Similarity threshold

        Returns:
            List of related evidence
        """
        return await self.search_similar(
            query=claim_text,
            collection_name="evidence",
            limit=limit,
            threshold=threshold,
        )

    async def find_similar_claims(
        self,
        claim_text: str,
        limit: int = 10,
        threshold: float = 0.8,
    ) -> List[Dict[str, Any]]:
        """Find similar claims.

        Args:
            claim_text: Claim to compare
            limit: Maximum results
            threshold: Similarity threshold

        Returns:
            List of similar claims
        """
        return await self.search_similar(
            query=claim_text,
            collection_name="claims",
            limit=limit,
            threshold=threshold,
        )

    async def find_papers_by_topic(
        self,
        topic: str,
        limit: int = 10,
        year_range: Optional[tuple[int, int]] = None,
    ) -> List[Dict[str, Any]]:
        """Find papers related to a topic.

        Args:
            topic: Topic to search for
            limit: Maximum results
            year_range: Optional (start_year, end_year) filter

        Returns:
            List of related papers
        """
        filters = {}
        if year_range:
            filters["metadata"] = {"year": {"$gte": year_range[0], "$lte": year_range[1]}}

        return await self.search_similar(
            query=topic,
            collection_name="papers",
            limit=limit,
            filters=filters,
        )

    def _select_model_for_collection(self, collection_name: str) -> str:
        """Select appropriate model for a collection.

        Args:
            collection_name: Collection name

        Returns:
            Model name
        """
        model_map = {
            "papers": "all-mpnet-base-v2",  # Best quality for full documents
            "evidence": "all-MiniLM-L12-v2",  # Good balance for snippets
            "claims": "all-MiniLM-L12-v2",  # Good balance for claims
            "sections": "all-MiniLM-L6-v2",  # Fast for section search
        }

        return model_map.get(collection_name, self.embedding_generator.default_model)

    async def reindex_collection(
        self,
        collection_name: str,
        batch_size: int = 100,
    ) -> None:
        """Reindex a collection for optimal performance.

        Args:
            collection_name: Collection to reindex
            batch_size: Batch size for processing
        """
        # Get collection stats
        stats = await self.vector_store.get_collection_stats(collection_name)
        logger.info(
            f"Reindexing collection '{collection_name}' with {stats['total_embeddings']} embeddings"
        )

        # Optimize indexes
        await self.vector_store.optimize_index(collection_name)

        logger.info(f"Completed reindexing of collection '{collection_name}'")
