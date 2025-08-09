"""Repository for Source model operations."""

import hashlib
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database.models import Source
from src.core.database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class SourceRepository(BaseRepository[Source]):
    """Repository for Source model with deduplication logic."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the SourceRepository.

        Args:
            session: The async database session
        """
        super().__init__(Source, session)

    @staticmethod
    def generate_fingerprint(csl_json: Dict[str, Any]) -> str:
        """Generate a fingerprint for a source based on its CSL-JSON.

        Uses DOI if available, otherwise creates hash from title + authors + year.

        Args:
            csl_json: CSL-JSON representation of the source

        Returns:
            SHA256 fingerprint string
        """
        # Use DOI if available
        if doi := csl_json.get("DOI"):
            return hashlib.sha256(doi.lower().encode()).hexdigest()

        # Otherwise, create fingerprint from key fields
        fingerprint_parts = []

        # Title
        if title := csl_json.get("title"):
            fingerprint_parts.append(title.lower().strip())

        # Authors
        authors = []
        for author in csl_json.get("author", []):
            if "family" in author:
                authors.append(author["family"].lower())
        if authors:
            fingerprint_parts.append("-".join(sorted(authors)))

        # Year
        if issued := csl_json.get("issued"):
            if date_parts := issued.get("date-parts"):
                if len(date_parts) > 0 and len(date_parts[0]) > 0:
                    fingerprint_parts.append(str(date_parts[0][0]))

        # Create hash from combined parts
        fingerprint_string = "|".join(fingerprint_parts)
        return hashlib.sha256(fingerprint_string.encode()).hexdigest()

    async def create_with_deduplication(
        self,
        run_id: UUID,
        csl_json: Dict[str, Any],
        connector_name: str,
        quality_score: Optional[float] = None,
        relevance_score: Optional[float] = None,
        raw_metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,  # Accept and ignore extra kwargs like schema_version
    ) -> Tuple[Source, bool]:
        """Create a source with deduplication.

        Args:
            run_id: The run ID
            csl_json: CSL-JSON representation
            connector_name: Name of the connector that found this source
            quality_score: Optional quality score
            relevance_score: Optional relevance score
            raw_metadata: Optional raw metadata from connector

        Returns:
            Tuple of (Source instance, is_new) where is_new indicates if it was created
        """
        fingerprint = self.generate_fingerprint(csl_json)

        try:
            # Try to create the source
            source = await self.create(
                run_id=run_id,
                fingerprint=fingerprint,
                csl_json=csl_json,
                connector_name=connector_name,
                quality_score=quality_score,
                relevance_score=relevance_score,
                raw_metadata=raw_metadata,
            )
            return source, True
        except IntegrityError:
            # Source already exists for this run, fetch it
            await self.session.rollback()
            existing = await self.get_by_fingerprint(run_id, fingerprint)
            if existing:
                # Update scores if new ones are better
                updates = {}
                if quality_score and (
                    not existing.quality_score or quality_score > existing.quality_score
                ):
                    updates["quality_score"] = quality_score
                if relevance_score and (
                    not existing.relevance_score or relevance_score > existing.relevance_score
                ):
                    updates["relevance_score"] = relevance_score

                if updates:
                    existing = await self.update(id=existing.id, **updates)  # type: ignore[arg-type]

                return existing, False  # type: ignore[return-value]
            else:
                # This shouldn't happen, but handle it
                raise

    async def bulk_create_with_deduplication(
        self, run_id: UUID, sources_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Bulk create sources with deduplication.

        Args:
            run_id: The run ID
            sources_data: List of source data dictionaries

        Returns:
            Dictionary with created sources and statistics
        """
        created_sources = []
        updated_sources = []
        errors = []

        for source_data in sources_data:
            try:
                source, is_new = await self.create_with_deduplication(run_id=run_id, **source_data)
                if is_new:
                    created_sources.append(source)
                else:
                    updated_sources.append(source)
            except Exception as e:
                logger.error("Error processing source")
                errors.append({"source_data": source_data, "error": str(e)})

        return {
            "created": created_sources,
            "updated": updated_sources,
            "errors": errors,
            "total_processed": len(sources_data),
            "total_created": len(created_sources),
            "total_updated": len(updated_sources),
            "total_errors": len(errors),
        }

    async def get_by_fingerprint(self, run_id: UUID, fingerprint: str) -> Optional[Source]:
        """Get a source by its fingerprint for a specific run.

        Args:
            run_id: The run ID
            fingerprint: The source fingerprint

        Returns:
            Source instance or None
        """
        try:
            query = select(Source).where(
                and_(Source.run_id == run_id, Source.fingerprint == fingerprint)
            )
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"Error fetching source by fingerprint: {e}")
            raise

    async def get_sources_by_quality(
        self,
        run_id: UUID,
        min_quality_score: float = 0.0,
        skip: int = 0,
        limit: int = 100,
        include_evidence: bool = False,
    ) -> List[Source]:
        """Get sources filtered by quality score.

        Args:
            run_id: The run ID
            min_quality_score: Minimum quality score
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_evidence: Whether to eager load evidence

        Returns:
            List of Source instances
        """
        try:
            query = (
                select(Source)
                .where(and_(Source.run_id == run_id, Source.quality_score >= min_quality_score))
                .order_by(Source.quality_score.desc())
                .offset(skip)
                .limit(limit)
            )

            if include_evidence:
                query = query.options(selectinload(Source.evidence))

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching sources by quality: {e}")
            raise

    async def get_sources_by_connector(self, run_id: UUID, connector_name: str) -> List[Source]:
        """Get all sources from a specific connector.

        Args:
            run_id: The run ID
            connector_name: Name of the connector

        Returns:
            List of Source instances
        """
        try:
            query = (
                select(Source)
                .where(and_(Source.run_id == run_id, Source.connector_name == connector_name))
                .order_by(Source.created_at)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching sources by connector: {e}")
            raise

    async def update_scores(
        self,
        source_id: UUID,
        quality_score: Optional[float] = None,
        relevance_score: Optional[float] = None,
    ) -> Optional[Source]:
        """Update quality and/or relevance scores for a source.

        Args:
            source_id: The source ID
            quality_score: New quality score
            relevance_score: New relevance score

        Returns:
            Updated Source instance or None
        """
        updates = {}
        if quality_score is not None:
            updates["quality_score"] = quality_score
        if relevance_score is not None:
            updates["relevance_score"] = relevance_score

        if updates:
            return await self.update(source_id, **updates)
        return await self.get_by_id(source_id)

    async def get_duplicate_sources(self, run_id: UUID) -> List[Dict[str, Any]]:
        """Find sources that appear in multiple connectors.

        Args:
            run_id: The run ID

        Returns:
            List of dictionaries with fingerprint and connector info
        """
        try:
            # Subquery to count connectors per fingerprint
            subquery = (
                select(
                    Source.fingerprint,
                    func.count(func.distinct(Source.connector_name)).label("connector_count"),
                    func.array_agg(func.distinct(Source.connector_name)).label("connectors"),
                )
                .where(Source.run_id == run_id)
                .group_by(Source.fingerprint)
                .having(func.count(func.distinct(Source.connector_name)) > 1)
                .subquery()
            )

            # Main query to get source details
            query = (
                select(Source, subquery.c.connector_count, subquery.c.connectors)
                .join(subquery, Source.fingerprint == subquery.c.fingerprint)
                .where(Source.run_id == run_id)
                .order_by(subquery.c.connector_count.desc())
            )

            result = await self.session.execute(query)

            duplicates = []
            for source, connector_count, connectors in result:
                duplicates.append(
                    {"source": source, "connector_count": connector_count, "connectors": connectors}
                )

            return duplicates
        except SQLAlchemyError as e:
            logger.error(f"Error finding duplicate sources: {e}")
            raise
