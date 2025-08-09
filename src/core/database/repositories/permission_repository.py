"""Repository for Permission operations."""

from typing import List, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.models import Permission
from src.core.database.repositories.base import BaseRepository


class PermissionRepository(BaseRepository[Permission]):
    """Repository for managing permissions."""

    def __init__(self, session: AsyncSession):
        """Initialize permission repository.

        Args:
            session: Async database session
        """
        super().__init__(Permission, session)

    async def get_by_resource_action(self, resource: str, action: str) -> Optional[Permission]:
        """Get permission by resource and action.

        Args:
            resource: Resource name
            action: Action name

        Returns:
            Permission if found, None otherwise
        """
        query = select(Permission).where(
            and_(Permission.resource == resource, Permission.action == action)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_resource(self, resource: str) -> List[Permission]:
        """Get all permissions for a resource.

        Args:
            resource: Resource name

        Returns:
            List of permissions for the resource
        """
        query = select(Permission).where(Permission.resource == resource)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_action(self, action: str) -> List[Permission]:
        """Get all permissions for an action.

        Args:
            action: Action name

        Returns:
            List of permissions for the action
        """
        query = select(Permission).where(Permission.action == action)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_permission(
        self, resource: str, action: str, description: Optional[str] = None
    ) -> Permission:
        """Create a new permission.

        Args:
            resource: Resource name
            action: Action name
            description: Optional permission description

        Returns:
            Created permission
        """
        # Check if already exists
        existing = await self.get_by_resource_action(resource, action)
        if existing:
            return existing

        # Create new permission
        permission_data = {"resource": resource, "action": action, "description": description}
        return await self.create(**permission_data)

    async def get_all_resources(self) -> List[str]:
        """Get all unique resource names.

        Returns:
            List of unique resource names
        """
        query = select(Permission.resource).distinct()
        result = await self.session.execute(query)
        return [row[0] for row in result]

    async def get_all_actions(self) -> List[str]:
        """Get all unique action names.

        Returns:
            List of unique action names
        """
        query = select(Permission.action).distinct()
        result = await self.session.execute(query)
        return [row[0] for row in result]
