"""FastAPI authentication dependencies."""

from typing import Annotated, Any, List, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.jwt_handler import TokenError, jwt_handler
from src.core.database.connection import get_async_db
from src.core.database.models import User
from src.core.database.repositories.user_repository import UserRepository

# Security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    session: Annotated[AsyncSession, Depends(get_async_db)],
) -> User:
    """Get current authenticated user from JWT token.

    Args:
        credentials: Bearer token from Authorization header
        session: Database session

    Returns:
        Current user object

    Raises:
        HTTPException: If authentication fails
    """
    token = credentials.credentials

    try:
        # Verify token and get user info
        user_info = jwt_handler.get_current_user(token)
        user_id = user_info["user_id"]

        # Get user from database
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return user

    except TokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_active_user(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Get current active user.

    Args:
        current_user: Current authenticated user

    Returns:
        Current user if active

    Raises:
        HTTPException: If user is not active
    """
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return current_user


def require_roles(required_roles: List[str]) -> Any:
    """Create a dependency that requires specific roles.

    Args:
        required_roles: List of required roles (user must have at least one)

    Returns:
        Dependency function that checks roles
    """

    async def role_checker(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
        """Check if user has required roles.

        Args:
            current_user: Current authenticated user

        Returns:
            Current user if authorized

        Raises:
            HTTPException: If user lacks required roles
        """
        user_roles: List[str] = current_user.roles if isinstance(current_user.roles, list) else []  # type: ignore[unreachable]

        # Check if user has at least one required role
        if not any(role in user_roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User lacks required roles: {required_roles}",
            )

        return current_user

    return role_checker


def require_verified_user(current_user: Annotated[User, Depends(get_current_active_user)]) -> User:
    """Require user to be verified.

    Args:
        current_user: Current authenticated user

    Returns:
        Current user if verified

    Raises:
        HTTPException: If user is not verified
    """
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Email verification required"
        )
    return current_user


# Commonly used role dependencies
require_admin = require_roles(["admin"])
require_researcher = require_roles(["researcher", "admin"])
require_reviewer = require_roles(["reviewer", "admin"])


async def get_optional_current_user(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials], Depends(HTTPBearer(auto_error=False))
    ],
    session: Annotated[AsyncSession, Depends(get_async_db)],
) -> Optional[User]:
    """Get current user if authenticated, None otherwise.

    Args:
        credentials: Optional bearer token
        session: Database session

    Returns:
        Current user or None
    """
    if not credentials:
        return None

    try:
        # Verify token and get user info
        user_info = jwt_handler.get_current_user(credentials.credentials)
        user_id = user_info["user_id"]

        # Get user from database
        user_repo = UserRepository(session)
        user = await user_repo.get_by_id(user_id)

        return user

    except Exception:
        # Return None for any auth errors
        return None
