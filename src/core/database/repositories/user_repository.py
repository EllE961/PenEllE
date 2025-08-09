"""Repository for User operations."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.models import User
from src.core.database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for managing users."""

    def __init__(self, session: AsyncSession):
        """Initialize user repository.

        Args:
            session: Async database session
        """
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email.

        Args:
            email: User email

        Returns:
            User if found, None otherwise
        """
        query = select(User).where(User.email == email)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_active_users(self) -> List[User]:
        """Get all active users.

        Returns:
            List of active users
        """
        query = select(User).where(User.is_active)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_role(self, role: str) -> List[User]:
        """Get users by role.

        Args:
            role: Role name

        Returns:
            List of users with the specified role
        """
        query = select(User).where(User.roles.contains([role]))
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_password(self, user_id: UUID, hashed_password: str) -> Optional[User]:
        """Update user password.

        Args:
            user_id: User ID
            hashed_password: New hashed password

        Returns:
            Updated user if successful
        """
        return await self.update(id=user_id, hashed_password=hashed_password)

    async def verify_user(self, user_id: UUID) -> Optional[User]:
        """Mark user as verified.

        Args:
            user_id: User ID

        Returns:
            Updated user if successful
        """
        return await self.update(id=user_id, is_verified=True)

    async def activate_user(self, user_id: UUID) -> Optional[User]:
        """Activate a user.

        Args:
            user_id: User ID

        Returns:
            Updated user if successful
        """
        return await self.update(id=user_id, is_active=True)

    async def deactivate_user(self, user_id: UUID) -> Optional[User]:
        """Deactivate a user.

        Args:
            user_id: User ID

        Returns:
            Updated user if successful
        """
        return await self.update(id=user_id, is_active=False)

    async def add_role(self, user_id: UUID, role: str) -> Optional[User]:
        """Add a role to user.

        Args:
            user_id: User ID
            role: Role to add

        Returns:
            Updated user if successful
        """
        user = await self.get_by_id(user_id)
        if user:
            current_roles: List[str] = user.roles if isinstance(user.roles, list) else []  # type: ignore[unreachable]
            if role not in current_roles:
                roles = current_roles.copy()
                roles.append(role)
                return await self.update(id=user_id, roles=roles)
        return user

    async def remove_role(self, user_id: UUID, role: str) -> Optional[User]:
        """Remove a role from user.

        Args:
            user_id: User ID
            role: Role to remove

        Returns:
            Updated user if successful
        """
        user = await self.get_by_id(user_id)
        if user:
            current_roles: List[str] = user.roles if isinstance(user.roles, list) else []  # type: ignore[unreachable]
            if role in current_roles:
                roles = current_roles.copy()
                roles.remove(role)
                return await self.update(id=user_id, roles=roles)
        return user
