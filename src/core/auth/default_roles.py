"""Default roles and permissions for PenEllE RBAC system."""

from typing import Any, Dict, List

# Resource types in the system
RESOURCES = [
    "runs",
    "artifacts",
    "users",
    "roles",
    "templates",
    "system",
    "sources",
    "evidence",
    "claims",
    "quality",
]

# Action types
ACTIONS = [
    "create",
    "read",
    "update",
    "delete",
    "execute",
    "approve",
    "admin",  # Full control over resource
]

# Default role definitions based on PenEllE spec section 12.6
DEFAULT_ROLES: Dict[str, Dict[str, Any]] = {
    "owner": {
        "description": "Full tenant control - can do everything",
        "permissions": ["*:*"],  # Wildcard - all permissions
    },
    "admin": {
        "description": "Manage users, roles, and templates - no document access",
        "permissions": [
            "users:*",
            "roles:*",
            "templates:*",
            "system:read",
            "system:update",
        ],
    },
    "operator": {
        "description": "Manage pipeline operations - no document access",
        "permissions": [
            "runs:create",
            "runs:read",
            "runs:update",
            "runs:execute",
            "system:read",
            "templates:read",
        ],
    },
    "reviewer": {
        "description": "Read artifacts, comment, and approve",
        "permissions": [
            "runs:read",
            "artifacts:read",
            "artifacts:approve",
            "sources:read",
            "evidence:read",
            "claims:read",
            "quality:read",
            "quality:approve",
        ],
    },
    "author": {
        "description": "Create runs and manage own artifacts",
        "permissions": [
            "runs:create",
            "runs:read",  # Own runs via ownership check
            "runs:update",  # Own runs via ownership check
            "runs:delete",  # Own runs via ownership check
            "artifacts:create",
            "artifacts:read",  # Own artifacts via ownership check
            "artifacts:update",  # Own artifacts via ownership check
            "sources:create",
            "sources:read",
            "evidence:create",
            "evidence:read",
            "claims:create",
            "claims:read",
            "templates:read",
        ],
    },
    "viewer": {
        "description": "Read-only access to public resources",
        "permissions": [
            "runs:read",  # Public runs only
            "artifacts:read",  # Public artifacts only
            "sources:read",
            "evidence:read",
            "claims:read",
            "quality:read",
            "templates:read",
        ],
    },
}


def get_all_permissions() -> List[str]:
    """Get all possible permissions in the system.

    Returns:
        List of all permission strings
    """
    permissions = []
    for resource in RESOURCES:
        for action in ACTIONS:
            permissions.append(f"{resource}:{action}")

    # Add wildcards
    permissions.append("*:*")
    for resource in RESOURCES:
        permissions.append(f"{resource}:*")
    for action in ACTIONS:
        permissions.append(f"*:{action}")

    return sorted(permissions)


def get_role_permissions(role_name: str) -> List[str]:
    """Get permissions for a specific role.

    Args:
        role_name: Name of the role

    Returns:
        List of permission strings for the role
    """
    role = DEFAULT_ROLES.get(role_name)
    return list(role["permissions"]) if role else []


def get_role_description(role_name: str) -> str:
    """Get description for a specific role.

    Args:
        role_name: Name of the role

    Returns:
        Role description
    """
    role = DEFAULT_ROLES.get(role_name)
    return str(role["description"]) if role else ""


# Permission helpers for common checks
class Permissions:
    """Common permission constants."""

    # Run permissions
    RUN_CREATE = "runs:create"
    RUN_READ = "runs:read"
    RUN_UPDATE = "runs:update"
    RUN_DELETE = "runs:delete"
    RUN_EXECUTE = "runs:execute"

    # Artifact permissions
    ARTIFACT_CREATE = "artifacts:create"
    ARTIFACT_READ = "artifacts:read"
    ARTIFACT_UPDATE = "artifacts:update"
    ARTIFACT_DELETE = "artifacts:delete"
    ARTIFACT_APPROVE = "artifacts:approve"

    # User permissions
    USER_CREATE = "users:create"
    USER_READ = "users:read"
    USER_UPDATE = "users:update"
    USER_DELETE = "users:delete"
    USER_ADMIN = "users:admin"

    # Role permissions
    ROLE_CREATE = "roles:create"
    ROLE_READ = "roles:read"
    ROLE_UPDATE = "roles:update"
    ROLE_DELETE = "roles:delete"
    ROLE_ADMIN = "roles:admin"

    # System permissions
    SYSTEM_READ = "system:read"
    SYSTEM_UPDATE = "system:update"
    SYSTEM_ADMIN = "system:admin"

    # Quality permissions
    QUALITY_READ = "quality:read"
    QUALITY_APPROVE = "quality:approve"

    # Wildcard permissions
    ALL_PERMISSIONS = "*:*"
    ALL_RUNS = "runs:*"
    ALL_ARTIFACTS = "artifacts:*"
    ALL_USERS = "users:*"
    ALL_ROLES = "roles:*"
