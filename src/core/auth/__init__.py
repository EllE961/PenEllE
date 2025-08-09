"""Authentication module for PenEllE."""

from .decorators import (
    can_approve,
    can_create,
    can_delete,
    can_execute,
    can_read,
    can_update,
    require_any_role,
    require_permission,
    require_resource_owner,
    require_role,
)
from .default_roles import (
    ACTIONS,
    DEFAULT_ROLES,
    RESOURCES,
    Permissions,
    get_all_permissions,
    get_role_description,
    get_role_permissions,
)
from .dependencies import (
    get_current_active_user,
    get_current_user,
    get_optional_current_user,
    require_admin,
    require_researcher,
    require_reviewer,
    require_roles,
    require_verified_user,
)
from .jwt_handler import JWTHandler, TokenError, jwt_handler
from .password import (
    generate_reset_token,
    generate_secure_password,
    hash_password,
    is_strong_password,
    verify_password,
)
from .rbac import RBACManager

__all__ = [
    # JWT
    "JWTHandler",
    "TokenError",
    "jwt_handler",
    # Password
    "hash_password",
    "verify_password",
    "generate_reset_token",
    "is_strong_password",
    "generate_secure_password",
    # Dependencies
    "get_current_user",
    "get_current_active_user",
    "get_optional_current_user",
    "require_roles",
    "require_verified_user",
    "require_admin",
    "require_researcher",
    "require_reviewer",
    # RBAC
    "RBACManager",
    "require_permission",
    "require_role",
    "require_any_role",
    "require_resource_owner",
    "can_create",
    "can_read",
    "can_update",
    "can_delete",
    "can_execute",
    "can_approve",
    # Default roles
    "DEFAULT_ROLES",
    "RESOURCES",
    "ACTIONS",
    "Permissions",
    "get_all_permissions",
    "get_role_permissions",
    "get_role_description",
]
