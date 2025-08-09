"""Role-Based Access Control (RBAC) Manager."""

import logging
from typing import List, Optional, Set
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.models import Permission, Role
from src.core.database.repositories import (
    PermissionRepository,
    RoleRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)


class RBACManager:
    """Manages role-based access control operations."""

    def __init__(self, session: AsyncSession):
        """Initialize RBAC manager.

        Args:
            session: Database session
        """
        self.session = session
        self.user_repo = UserRepository(session)
        self.role_repo = RoleRepository(session)
        self.permission_repo = PermissionRepository(session)
        self._permission_cache: dict = {}

    async def assign_role_to_user(self, user_id: str, role_name: str) -> bool:
        """Assign a role to a user.

        Args:
            user_id: User ID
            role_name: Name of the role to assign

        Returns:
            True if successful, False otherwise
        """
        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

            # Get role by name
            role = await self.role_repo.get_by_name(role_name)
            if not role:
                logger.warning(f"Role not found: {role_name}")
                return False

            # Check if user exists
            user = await self.user_repo.get_by_id(user_uuid)
            if not user:
                logger.warning(f"User not found: {user_id}")
                return False

            # Assign role
            success = await self.role_repo.assign_role_to_user(user_uuid, role.id)  # type: ignore[arg-type]
            if success:
                logger.info(f"Assigned role {role_name} to user {user_id}")
            else:
                logger.info(f"User {user_id} already has role {role_name}")

            return success

        except Exception as e:
            logger.error(f"Error assigning role: {e}")
            return False

    async def remove_role_from_user(self, user_id: str, role_name: str) -> bool:
        """Remove a role from a user.

        Args:
            user_id: User ID
            role_name: Name of the role to remove

        Returns:
            True if successful, False otherwise
        """
        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

            # Get role by name
            role = await self.role_repo.get_by_name(role_name)
            if not role:
                logger.warning(f"Role not found: {role_name}")
                return False

            # Remove role
            success = await self.role_repo.remove_role_from_user(user_uuid, role.id)  # type: ignore[arg-type]
            if success:
                logger.info(f"Removed role {role_name} from user {user_id}")
            else:
                logger.info(f"User {user_id} doesn't have role {role_name}")

            return success

        except Exception as e:
            logger.error(f"Error removing role: {e}")
            return False

    async def get_user_roles(self, user_id: str) -> List[Role]:
        """Get all roles assigned to a user.

        Args:
            user_id: User ID

        Returns:
            List of roles
        """
        try:
            user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
            return await self.role_repo.get_user_roles(user_uuid)
        except Exception as e:
            logger.error(f"Error getting user roles: {e}")
            return []

    async def get_user_permissions(self, user_id: str) -> List[str]:
        """Get all permissions for a user through their roles.

        Args:
            user_id: User ID

        Returns:
            List of permission strings
        """
        try:
            # Get user roles
            roles = await self.get_user_roles(user_id)

            # Collect all permissions
            permissions_set: Set[str] = set()
            for role in roles:
                if role.permissions:
                    permissions_set.update(role.permissions)

            return sorted(list(permissions_set))

        except Exception as e:
            logger.error(f"Error getting user permissions: {e}")
            return []

    async def has_permission(self, user_id: str, resource: str, action: str) -> bool:
        """Check if user has a specific permission.

        Args:
            user_id: User ID
            resource: Resource name
            action: Action name

        Returns:
            True if user has permission
        """
        try:
            # Build permission string
            permission = f"{resource}:{action}"

            # Get user permissions
            user_permissions = await self.get_user_permissions(user_id)

            # Check specific permission
            if permission in user_permissions:
                return True

            # Check wildcard permissions
            if f"{resource}:*" in user_permissions:  # All actions on resource
                return True
            if f"*:{action}" in user_permissions:  # Action on all resources
                return True
            if "*:*" in user_permissions:  # Super admin
                return True

            return False

        except Exception as e:
            logger.error(f"Error checking permission: {e}")
            return False

    async def has_role(self, user_id: str, role_name: str) -> bool:
        """Check if user has a specific role.

        Args:
            user_id: User ID
            role_name: Role name to check

        Returns:
            True if user has the role
        """
        try:
            roles = await self.get_user_roles(user_id)
            return any(role.name == role_name for role in roles)
        except Exception as e:
            logger.error(f"Error checking role: {e}")
            return False

    async def create_role(
        self, name: str, permissions: List[str], description: Optional[str] = None
    ) -> Optional[Role]:
        """Create a new role.

        Args:
            name: Role name
            permissions: List of permission strings
            description: Optional role description

        Returns:
            Created role or None if failed
        """
        try:
            # Check if role already exists
            existing = await self.role_repo.get_by_name(name)
            if existing:
                logger.warning(f"Role already exists: {name}")
                return existing

            # Create role
            role_data = {"name": name, "permissions": permissions, "description": description}

            role = await self.role_repo.create(**role_data)
            logger.info(f"Created role: {name}")
            return role

        except Exception as e:
            logger.error(f"Error creating role: {e}")
            return None

    async def update_role_permissions(
        self, role_name: str, permissions: List[str]
    ) -> Optional[Role]:
        """Update permissions for a role.

        Args:
            role_name: Role name
            permissions: New list of permissions

        Returns:
            Updated role or None if failed
        """
        try:
            # Get role
            role = await self.role_repo.get_by_name(role_name)
            if not role:
                logger.warning(f"Role not found: {role_name}")
                return None

            # Update permissions
            updated_role = await self.role_repo.update_permissions(role.id, permissions)  # type: ignore[arg-type]

            if updated_role:
                logger.info(f"Updated permissions for role: {role_name}")

            return updated_role

        except Exception as e:
            logger.error(f"Error updating role permissions: {e}")
            return None

    async def create_permission(
        self, resource: str, action: str, description: Optional[str] = None
    ) -> Permission:
        """Create a new permission.

        Args:
            resource: Resource name
            action: Action name
            description: Optional description

        Returns:
            Created permission
        """
        return await self.permission_repo.create_permission(resource, action, description)

    async def get_all_permissions(self) -> List[Permission]:
        """Get all permissions in the system.

        Returns:
            List of all permissions
        """
        return await self.permission_repo.get_all()

    async def get_permissions_for_resource(self, resource: str) -> List[Permission]:
        """Get all permissions for a resource.

        Args:
            resource: Resource name

        Returns:
            List of permissions
        """
        return await self.permission_repo.get_by_resource(resource)
