"""Repository for Evidence model operations."""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database.models import Evidence
from src.core.database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class EvidenceRepository(BaseRepository[Evidence]):
    """Repository for Evidence model with filtering capabilities."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the EvidenceRepository.

        Args:
            session: The async database session
        """
        super().__init__(Evidence, session)

    async def get_evidence_by_type(
        self,
        run_id: UUID,
        evidence_type: str,
        skip: int = 0,
        limit: int = 100,
        include_source: bool = False,
    ) -> List[Evidence]:
        """Get evidence filtered by type.

        Args:
            run_id: The run ID
            evidence_type: Type of evidence to filter
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_source: Whether to eager load source

        Returns:
            List of Evidence instances
        """
        try:
            query = (
                select(Evidence)
                .where(and_(Evidence.run_id == run_id, Evidence.evidence_type == evidence_type))
                .order_by(Evidence.confidence_score.desc())
                .offset(skip)
                .limit(limit)
            )

            if include_source:
                query = query.options(selectinload(Evidence.source))

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching evidence by type {evidence_type}: {e}")
            raise

    async def get_evidence_by_section(
        self,
        run_id: UUID,
        section_id: str,
        min_confidence: float = 0.0,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Evidence]:
        """Get evidence relevant to a specific section.

        Args:
            run_id: The run ID
            section_id: Section identifier
            min_confidence: Minimum confidence score
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of Evidence instances
        """
        try:
            # This would typically join with a mapping table or use metadata
            # For now, we'll filter by metadata field
            query = (
                select(Evidence)
                .where(
                    and_(
                        Evidence.run_id == run_id,
                        Evidence.confidence_score >= min_confidence,
                        Evidence.extraction_metadata["section_id"].astext == section_id,
                    )
                )
                .order_by(Evidence.confidence_score.desc())
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching evidence by section {section_id}: {e}")
            raise

    async def get_evidence_by_source(
        self, source_id: UUID, evidence_type: Optional[str] = None, min_confidence: float = 0.0
    ) -> List[Evidence]:
        """Get all evidence from a specific source.

        Args:
            source_id: The source ID
            evidence_type: Optional type filter
            min_confidence: Minimum confidence score

        Returns:
            List of Evidence instances
        """
        try:
            conditions = [
                Evidence.source_id == source_id,
                Evidence.confidence_score >= min_confidence,
            ]

            if evidence_type:
                conditions.append(Evidence.evidence_type == evidence_type)

            query = (
                select(Evidence)
                .where(and_(*conditions))
                .order_by(Evidence.location["page"].astext, Evidence.location["paragraph"].astext)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching evidence by source {source_id}: {e}")
            raise

    async def get_high_confidence_evidence(
        self,
        run_id: UUID,
        min_confidence: float = 0.8,
        skip: int = 0,
        limit: int = 100,
        include_claims: bool = False,
    ) -> List[Evidence]:
        """Get evidence with high confidence scores.

        Args:
            run_id: The run ID
            min_confidence: Minimum confidence threshold
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_claims: Whether to eager load related claims

        Returns:
            List of Evidence instances
        """
        try:
            query = (
                select(Evidence)
                .where(and_(Evidence.run_id == run_id, Evidence.confidence_score >= min_confidence))
                .order_by(Evidence.confidence_score.desc())
                .offset(skip)
                .limit(limit)
            )

            if include_claims:
                query = query.options(selectinload(Evidence.claims))

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching high confidence evidence: {e}")
            raise

    async def get_evidence_statistics(self, run_id: UUID) -> Dict[str, Any]:
        """Get statistics about evidence for a run.

        Args:
            run_id: The run ID

        Returns:
            Dictionary with evidence statistics
        """
        try:
            # Count by type
            type_counts_query = (
                select(Evidence.evidence_type, func.count(Evidence.id).label("count"))
                .where(Evidence.run_id == run_id)
                .group_by(Evidence.evidence_type)
            )
            type_result = await self.session.execute(type_counts_query)
            type_counts = {row.evidence_type: row.count for row in type_result}

            # Average confidence by type
            avg_confidence_query = (
                select(
                    Evidence.evidence_type,
                    func.avg(Evidence.confidence_score).label("avg_confidence"),
                )
                .where(Evidence.run_id == run_id)
                .group_by(Evidence.evidence_type)
            )
            confidence_result = await self.session.execute(avg_confidence_query)
            avg_confidence = {
                row.evidence_type: float(row.avg_confidence) for row in confidence_result
            }

            # Total count
            total_query = select(func.count(Evidence.id)).where(Evidence.run_id == run_id)
            total_result = await self.session.execute(total_query)
            total_count = total_result.scalar() or 0

            # Count by source
            source_counts_query = (
                select(Evidence.source_id, func.count(Evidence.id).label("count"))
                .where(Evidence.run_id == run_id)
                .group_by(Evidence.source_id)
                .order_by(func.count(Evidence.id).desc())
                .limit(10)  # Top 10 sources
            )
            source_result = await self.session.execute(source_counts_query)
            top_sources = [
                {"source_id": str(row.source_id), "count": row.count} for row in source_result
            ]

            return {
                "total_count": total_count,
                "by_type": type_counts,
                "average_confidence_by_type": avg_confidence,
                "top_sources": top_sources,
                "overall_average_confidence": (
                    sum(avg_confidence.values()) / len(avg_confidence) if avg_confidence else 0
                ),
            }
        except SQLAlchemyError as e:
            logger.error(f"Error calculating evidence statistics: {e}")
            raise

    async def search_evidence(
        self,
        run_id: UUID,
        search_term: str,
        evidence_types: Optional[List[str]] = None,
        min_confidence: float = 0.0,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Evidence]:
        """Search evidence content for a term.

        Args:
            run_id: The run ID
            search_term: Term to search for in content
            evidence_types: Optional list of types to filter
            min_confidence: Minimum confidence score
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of Evidence instances
        """
        try:
            conditions = [
                Evidence.run_id == run_id,
                Evidence.confidence_score >= min_confidence,
                Evidence.content.ilike(f"%{search_term}%"),
            ]

            if evidence_types:
                conditions.append(Evidence.evidence_type.in_(evidence_types))

            query = (
                select(Evidence)
                .where(and_(*conditions))
                .order_by(Evidence.confidence_score.desc())
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error searching evidence: {e}")
            raise

    async def get_evidence_with_embeddings(
        self,
        run_id: UUID,
        model_name: str,
        embedding_type: str = "content",
        skip: int = 0,
        limit: int = 100,
    ) -> List[Evidence]:
        """Get evidence that has embeddings from a specific model.

        Args:
            run_id: The run ID
            model_name: Name of the embedding model
            embedding_type: Type of embedding
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of Evidence instances with embeddings loaded
        """
        try:
            query = (
                select(Evidence)
                .where(Evidence.run_id == run_id)
                .join(Evidence.embeddings)
                .where(
                    and_(
                        Evidence.embeddings.any(
                            and_(
                                Evidence.embeddings.property.mapper.class_.model_name == model_name,
                                Evidence.embeddings.property.mapper.class_.embedding_type
                                == embedding_type,
                            )
                        )
                    )
                )
                .options(selectinload(Evidence.embeddings))
                .order_by(Evidence.created_at)
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching evidence with embeddings: {e}")
            raise
