"""Repository for Claim model operations."""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database.models import Claim, ClaimEvidence
from src.core.database.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ClaimRepository(BaseRepository[Claim]):
    """Repository for Claim model with graph queries."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize the ClaimRepository.

        Args:
            session: The async database session
        """
        super().__init__(Claim, session)

    async def get_claims_by_section(
        self,
        run_id: UUID,
        section_id: str,
        skip: int = 0,
        limit: int = 100,
        include_evidence: bool = False,
    ) -> List[Claim]:
        """Get claims for a specific section.

        Args:
            run_id: The run ID
            section_id: Section identifier
            skip: Number of records to skip
            limit: Maximum number of records to return
            include_evidence: Whether to eager load evidence links

        Returns:
            List of Claim instances ordered by location
        """
        try:
            query = (
                select(Claim)
                .where(and_(Claim.run_id == run_id, Claim.section_id == section_id))
                .order_by(Claim.paragraph_index, Claim.sentence_index)
                .offset(skip)
                .limit(limit)
            )

            if include_evidence:
                query = query.options(
                    selectinload(Claim.evidence_links).selectinload(ClaimEvidence.evidence)
                )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching claims by section {section_id}: {e}")
            raise

    async def get_claims_by_type(
        self,
        run_id: UUID,
        claim_type: str,
        min_confidence: float = 0.0,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Claim]:
        """Get claims filtered by type.

        Args:
            run_id: The run ID
            claim_type: Type of claim
            min_confidence: Minimum confidence score
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of Claim instances
        """
        try:
            query = (
                select(Claim)
                .where(
                    and_(
                        Claim.run_id == run_id,
                        Claim.claim_type == claim_type,
                        Claim.confidence_score >= min_confidence,
                    )
                )
                .order_by(Claim.confidence_score.desc())
                .offset(skip)
                .limit(limit)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching claims by type {claim_type}: {e}")
            raise

    async def get_unsupported_claims(
        self, run_id: UUID, min_confidence: float = 0.5
    ) -> List[Claim]:
        """Get claims that have no supporting evidence.

        Args:
            run_id: The run ID
            min_confidence: Minimum confidence score

        Returns:
            List of unsupported Claim instances
        """
        try:
            # Subquery to find claims with evidence
            supported_claims = select(ClaimEvidence.claim_id).distinct().subquery()

            query = (
                select(Claim)
                .where(
                    and_(
                        Claim.run_id == run_id,
                        Claim.confidence_score >= min_confidence,
                        ~Claim.id.in_(supported_claims),  # type: ignore[arg-type]
                    )
                )
                .order_by(Claim.section_id, Claim.paragraph_index, Claim.sentence_index)
            )

            result = await self.session.execute(query)
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"Error fetching unsupported claims: {e}")
            raise

    async def get_claim_graph(
        self, run_id: UUID, section_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Build a graph representation of claims and their evidence.

        Args:
            run_id: The run ID
            section_id: Optional section filter

        Returns:
            Dictionary representing the claim-evidence graph
        """
        try:
            # Base query for claims
            claim_conditions = [Claim.run_id == run_id]
            if section_id:
                claim_conditions.append(Claim.section_id == section_id)

            # Get claims with evidence links
            claim_query = (
                select(Claim)
                .where(and_(*claim_conditions))
                .options(selectinload(Claim.evidence_links).selectinload(ClaimEvidence.evidence))
            )

            claim_result = await self.session.execute(claim_query)
            claims = list(claim_result.scalars().unique().all())

            # Build graph structure
            nodes: Dict[str, List[Any]] = {"claims": [], "evidence": []}
            edges = []
            evidence_seen = set()

            for claim in claims:
                # Add claim node
                nodes["claims"].append(
                    {
                        "id": str(claim.id),
                        "text": claim.claim_text,
                        "type": claim.claim_type,
                        "section": claim.section_id,
                        "location": {
                            "paragraph": claim.paragraph_index,
                            "sentence": claim.sentence_index,
                        },
                        "confidence": claim.confidence_score,
                    }
                )

                # Add evidence nodes and edges
                for link in claim.evidence_links:
                    evidence = link.evidence

                    # Add evidence node if not seen
                    if evidence.id not in evidence_seen:
                        evidence_seen.add(evidence.id)
                        nodes["evidence"].append(
                            {
                                "id": str(evidence.id),
                                "type": evidence.evidence_type,
                                "content": (
                                    evidence.content[:200] + "..."
                                    if len(evidence.content) > 200
                                    else evidence.content
                                ),
                                "confidence": evidence.confidence_score,
                                "source_id": str(evidence.source_id),
                            }
                        )

                    # Add edge
                    edges.append(
                        {
                            "claim_id": str(claim.id),
                            "evidence_id": str(evidence.id),
                            "relevance": link.relevance_score,
                        }
                    )

            return {
                "run_id": str(run_id),
                "section_id": section_id,
                "nodes": nodes,
                "edges": edges,
                "statistics": {
                    "total_claims": len(nodes["claims"]),
                    "total_evidence": len(nodes["evidence"]),
                    "total_links": len(edges),
                    "avg_evidence_per_claim": (
                        len(edges) / len(nodes["claims"]) if nodes["claims"] else 0
                    ),
                },
            }
        except SQLAlchemyError as e:
            logger.error(f"Error building claim graph: {e}")
            raise

    async def link_claim_to_evidence(
        self, claim_id: UUID, evidence_id: UUID, relevance_score: float
    ) -> ClaimEvidence:
        """Create a link between a claim and evidence.

        Args:
            claim_id: The claim ID
            evidence_id: The evidence ID
            relevance_score: Relevance score (0-1)

        Returns:
            ClaimEvidence instance
        """
        try:
            link = ClaimEvidence(
                claim_id=claim_id, evidence_id=evidence_id, relevance_score=relevance_score
            )
            self.session.add(link)
            await self.session.flush()

            logger.info(f"Linked claim {claim_id} to evidence {evidence_id}")
            return link
        except SQLAlchemyError as e:
            logger.error(f"Error linking claim to evidence: {e}")
            await self.session.rollback()
            raise

    async def bulk_link_claims_to_evidence(
        self, links: List[Dict[str, Any]]
    ) -> List[ClaimEvidence]:
        """Create multiple claim-evidence links.

        Args:
            links: List of dictionaries with claim_id, evidence_id, and relevance_score

        Returns:
            List of ClaimEvidence instances
        """
        try:
            link_instances = [ClaimEvidence(**link) for link in links]
            self.session.add_all(link_instances)
            await self.session.flush()

            logger.info(f"Created {len(link_instances)} claim-evidence links")
            return link_instances
        except SQLAlchemyError as e:
            logger.error(f"Error in bulk linking claims to evidence: {e}")
            await self.session.rollback()
            raise

    async def get_claim_statistics(self, run_id: UUID) -> Dict[str, Any]:
        """Get statistics about claims for a run.

        Args:
            run_id: The run ID

        Returns:
            Dictionary with claim statistics
        """
        try:
            # Count by type
            type_counts_query = (
                select(Claim.claim_type, func.count(Claim.id).label("count"))
                .where(Claim.run_id == run_id)
                .group_by(Claim.claim_type)
            )
            type_result = await self.session.execute(type_counts_query)
            type_counts = {row.claim_type: row.count for row in type_result}

            # Count by section
            section_counts_query = (
                select(Claim.section_id, func.count(Claim.id).label("count"))
                .where(Claim.run_id == run_id)
                .group_by(Claim.section_id)
            )
            section_result = await self.session.execute(section_counts_query)
            section_counts = {row.section_id: row.count for row in section_result}

            # Average confidence
            avg_confidence_query = select(func.avg(Claim.confidence_score)).where(
                Claim.run_id == run_id
            )
            avg_result = await self.session.execute(avg_confidence_query)
            avg_confidence = avg_result.scalar() or 0

            # Claims with/without evidence
            with_evidence_query = (
                select(func.count(func.distinct(ClaimEvidence.claim_id)))
                .join(Claim, ClaimEvidence.claim_id == Claim.id)
                .where(Claim.run_id == run_id)
            )
            with_evidence_result = await self.session.execute(with_evidence_query)
            claims_with_evidence = with_evidence_result.scalar() or 0

            total_claims = sum(type_counts.values())  # type: ignore[arg-type]

            return {
                "total_claims": total_claims,
                "by_type": type_counts,
                "by_section": section_counts,
                "average_confidence": float(avg_confidence),
                "claims_with_evidence": claims_with_evidence,
                "claims_without_evidence": total_claims - claims_with_evidence,
                "evidence_coverage_rate": (
                    claims_with_evidence / total_claims * 100 if total_claims > 0 else 0
                ),
            }
        except SQLAlchemyError as e:
            logger.error(f"Error calculating claim statistics: {e}")
            raise

    async def find_contradictory_claims(
        self, run_id: UUID, similarity_threshold: float = 0.8
    ) -> List[Dict[str, Any]]:
        """Find potentially contradictory claims.

        This is a placeholder for more sophisticated NLI-based detection.

        Args:
            run_id: The run ID
            similarity_threshold: Threshold for considering claims similar

        Returns:
            List of potentially contradictory claim pairs
        """
        try:
            # For now, return empty list
            # In production, this would use embeddings and NLI models
            logger.info("Contradictory claim detection not yet implemented")
            return []
        except SQLAlchemyError as e:
            logger.error(f"Error finding contradictory claims: {e}")
            raise
