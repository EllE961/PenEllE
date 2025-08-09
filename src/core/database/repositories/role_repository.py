"""Repository for Role operations."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.database.models import Role, user_roles
from src.core.database.repositories.base import BaseRepository


class RoleRepository(BaseRepository[Role]):
    """Repository for managing roles."""

    def __init__(self, session: AsyncSession):
        """Initialize role repository.

        Args:
            session: Async database session
        """
        super().__init__(Role, session)

    async def get_by_name(self, name: str) -> Optional[Role]:
        """Get role by name.

        Args:
            name: Role name

        Returns:
            Role if found, None otherwise
        """
        query = select(Role).where(Role.name == name)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_with_users(self, role_id: UUID) -> Optional[Role]:
        """Get role with users loaded.

        Args:
            role_id: Role ID

        Returns:
            Role with users if found
        """
        query = select(Role).options(selectinload(Role.users)).where(Role.id == role_id)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_user_roles(self, user_id: UUID) -> List[Role]:
        """Get all roles for a user.

        Args:
            user_id: User ID

        Returns:
            List of roles assigned to the user
        """
        query = (
            select(Role)
            .join(user_roles, Role.id == user_roles.c.role_id)
            .where(user_roles.c.user_id == user_id)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def assign_role_to_user(self, user_id: UUID, role_id: UUID) -> bool:
        """Assign a role to a user.

        Args:
            user_id: User ID
            role_id: Role ID

        Returns:
            True if successful, False if already assigned
        """
        # Check if already assigned
        check_query = select(user_roles).where(
            user_roles.c.user_id == user_id, user_roles.c.role_id == role_id
        )
        result = await self.session.execute(check_query)
        if result.first():
            return False

        # Assign role
        stmt = user_roles.insert().values(user_id=user_id, role_id=role_id)
        await self.session.execute(stmt)
        await self.session.commit()
        return True

    async def remove_role_from_user(self, user_id: UUID, role_id: UUID) -> bool:
        """Remove a role from a user.

        Args:
            user_id: User ID
            role_id: Role ID

        Returns:
            True if removed, False if not assigned
        """
        stmt = user_roles.delete().where(
            user_roles.c.user_id == user_id, user_roles.c.role_id == role_id
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def update_permissions(self, role_id: UUID, permissions: List[str]) -> Optional[Role]:
        """Update role permissions.

        Args:
            role_id: Role ID
            permissions: New list of permissions

        Returns:
            Updated role if successful
        """
        return await self.update(role_id, permissions=permissions)

    async def add_permission(self, role_id: UUID, permission: str) -> Optional[Role]:
        """Add a permission to a role.

        Args:
            role_id: Role ID
            permission: Permission string to add

        Returns:
            Updated role if successful
        """
        role = await self.get_by_id(role_id)
        if role:
            current_permissions: List[str] = role.permissions if isinstance(role.permissions, list) else []  # type: ignore[unreachable]
            if permission not in current_permissions:
                permissions = current_permissions.copy()
                permissions.append(permission)
                return await self.update_permissions(role_id, permissions)
        return role

    async def remove_permission(self, role_id: UUID, permission: str) -> Optional[Role]:
        """Remove a permission from a role.

        Args:
            role_id: Role ID
            permission: Permission string to remove

        Returns:
            Updated role if successful
        """
        role = await self.get_by_id(role_id)
        if role:
            current_permissions: List[str] = role.permissions if isinstance(role.permissions, list) else []  # type: ignore[unreachable]
            if permission in current_permissions:
                permissions = current_permissions.copy()
                permissions.remove(permission)
                return await self.update_permissions(role_id, permissions)
        return role
