"""Permission decorators for FastAPI routes."""

from typing import Annotated, Any, Callable, List

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.dependencies import get_current_active_user
from src.core.auth.rbac import RBACManager
from src.core.database.connection import get_async_db
from src.core.database.models import User


def require_permission(resource: str, action: str) -> Callable:
    """Decorator to require specific permission for endpoint.

    Args:
        resource: Resource name
        action: Action name

    Returns:
        Dependency function

    Usage:
        @router.get("/runs", dependencies=[Depends(require_permission("runs", "read"))])
        async def list_runs():
            ...
    """

    async def permission_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
        session: Annotated[AsyncSession, Depends(get_async_db)],
    ) -> User:
        """Check if user has required permission.

        Args:
            current_user: Current authenticated user
            session: Database session

        Returns:
            Current user if authorized

        Raises:
            HTTPException: If user lacks permission
        """
        rbac = RBACManager(session)

        # Check permission
        has_perm = await rbac.has_permission(str(current_user.id), resource, action)

        if not has_perm:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {resource}:{action}",
            )

        return current_user

    return permission_checker


def require_role(role_name: str) -> Callable:
    """Decorator to require specific role for endpoint.

    Args:
        role_name: Required role name

    Returns:
        Dependency function

    Usage:
        @router.post("/admin/users", dependencies=[Depends(require_role("admin"))])
        async def create_user():
            ...
    """

    async def role_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
        session: Annotated[AsyncSession, Depends(get_async_db)],
    ) -> User:
        """Check if user has required role.

        Args:
            current_user: Current authenticated user
            session: Database session

        Returns:
            Current user if authorized

        Raises:
            HTTPException: If user lacks role
        """
        rbac = RBACManager(session)

        # Check role
        has_role = await rbac.has_role(str(current_user.id), role_name)

        if not has_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"Requires role: {role_name}"
            )

        return current_user

    return role_checker


def require_any_role(role_names: List[str]) -> Callable:
    """Decorator to require any of the specified roles.

    Args:
        role_names: List of acceptable role names

    Returns:
        Dependency function

    Usage:
        @router.get("/reports", dependencies=[Depends(require_any_role(["admin", "reviewer"]))])
        async def get_reports():
            ...
    """

    async def any_role_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
        session: Annotated[AsyncSession, Depends(get_async_db)],
    ) -> User:
        """Check if user has any of the required roles.

        Args:
            current_user: Current authenticated user
            session: Database session

        Returns:
            Current user if authorized

        Raises:
            HTTPException: If user lacks all roles
        """
        rbac = RBACManager(session)

        # Check if user has any of the roles
        for role_name in role_names:
            if await rbac.has_role(str(current_user.id), role_name):
                return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Requires one of roles: {', '.join(role_names)}",
        )

    return any_role_checker


# Convenience decorators for common permissions
def can_create(resource: str) -> Callable:
    """Require create permission on resource."""
    return require_permission(resource, "create")


def can_read(resource: str) -> Callable:
    """Require read permission on resource."""
    return require_permission(resource, "read")


def can_update(resource: str) -> Callable:
    """Require update permission on resource."""
    return require_permission(resource, "update")


def can_delete(resource: str) -> Callable:
    """Require delete permission on resource."""
    return require_permission(resource, "delete")


def can_execute(resource: str) -> Callable:
    """Require execute permission on resource."""
    return require_permission(resource, "execute")


def can_approve(resource: str) -> Callable:
    """Require approve permission on resource."""
    return require_permission(resource, "approve")


# Resource owner check decorator
def require_resource_owner(resource_type: str, get_resource_owner: Callable) -> Callable:
    """Decorator to ensure user owns the resource or has override permission.

    Args:
        resource_type: Type of resource (e.g., "runs", "artifacts")
        get_resource_owner: Async function to get resource owner ID

    Returns:
        Dependency function

    Usage:
        async def get_run_owner(run_id: str, session: AsyncSession) -> str:
            run = await run_repo.get(run_id)
            return str(run.user_id) if run else None

        @router.delete("/runs/{run_id}",
                      dependencies=[Depends(require_resource_owner("runs", get_run_owner))])
        async def delete_run(run_id: str):
            ...
    """

    async def owner_checker(
        current_user: Annotated[User, Depends(get_current_active_user)],
        session: Annotated[AsyncSession, Depends(get_async_db)],
        **kwargs: Any,
    ) -> User:
        """Check if user owns resource or has override permission.

        Args:
            current_user: Current authenticated user
            session: Database session
            **kwargs: Route parameters

        Returns:
            Current user if authorized

        Raises:
            HTTPException: If user doesn't own resource and lacks override
        """
        rbac = RBACManager(session)

        # Check if user has override permission (can access all resources)
        if await rbac.has_permission(str(current_user.id), resource_type, "admin"):
            return current_user

        # Get resource owner
        owner_id = await get_resource_owner(session=session, **kwargs)

        if not owner_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource_type} not found"
            )

        # Check ownership
        if str(current_user.id) != owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Not authorized to access this {resource_type[:-1]}",
            )

        return current_user

    return owner_checker
