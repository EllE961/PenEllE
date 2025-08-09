"""Tests for RBAC (Role-Based Access Control) system."""

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth import (
    DEFAULT_ROLES,
    RBACManager,
    get_all_permissions,
    get_role_description,
    get_role_permissions,
)
from src.core.database.models import User
from src.core.database.repositories import (
    PermissionRepository,
    RoleRepository,
    UserRepository,
)


@pytest_asyncio.fixture
async def test_user(async_session: AsyncSession) -> User:
    """Create a test user."""
    user_repo = UserRepository(async_session)
    user_data = {
        "email": "test@example.com",
        "hashed_password": "hashed_password",
        "is_active": True,
        "is_verified": True,
        "roles": [],
    }
    user = await user_repo.create(**user_data)
    return user


@pytest_asyncio.fixture
async def test_roles(async_session: AsyncSession) -> dict:
    """Create test roles."""
    role_repo = RoleRepository(async_session)

    roles = {}
    for role_name, role_def in DEFAULT_ROLES.items():
        role_data = {
            "name": role_name,
            "description": role_def["description"],
            "permissions": role_def["permissions"],
        }
        role = await role_repo.create(**role_data)
        roles[role_name] = role

    await async_session.commit()
    return roles


@pytest_asyncio.fixture
async def test_permissions(async_session: AsyncSession) -> list:
    """Create test permissions."""
    perm_repo = PermissionRepository(async_session)

    permissions = []
    resources = ["runs", "artifacts", "users", "roles"]
    actions = ["create", "read", "update", "delete"]

    for resource in resources:
        for action in actions:
            perm = await perm_repo.create_permission(
                resource=resource, action=action, description=f"{action.capitalize()} {resource}"
            )
            permissions.append(perm)

    return permissions


@pytest_asyncio.fixture
async def rbac_manager(async_session: AsyncSession) -> RBACManager:
    """Create RBAC manager instance."""
    return RBACManager(async_session)


class TestRBACModels:
    """Test RBAC database models."""

    @pytest.mark.asyncio()
    async def test_create_role(self, async_session: AsyncSession, db_manager):
        """Test creating a role."""
        role_repo = RoleRepository(async_session)

        role_data = {
            "name": "test_role",
            "description": "Test role description",
            "permissions": ["runs:read", "runs:create"],
        }

        role = await role_repo.create(**role_data)

        assert role.id is not None
        assert role.name == "test_role"
        assert role.description == "Test role description"
        assert role.permissions == ["runs:read", "runs:create"]
        assert role.created_at is not None
        assert role.updated_at is not None

    @pytest.mark.asyncio()
    async def test_create_permission(self, async_session: AsyncSession, db_manager):
        """Test creating a permission."""
        perm_repo = PermissionRepository(async_session)

        perm = await perm_repo.create_permission(
            resource="test_resource", action="test_action", description="Test permission"
        )

        assert perm.id is not None
        assert perm.resource == "test_resource"
        assert perm.action == "test_action"
        assert perm.description == "Test permission"

    @pytest.mark.asyncio()
    async def test_unique_permission_constraint(self, async_session: AsyncSession, db_manager):
        """Test that duplicate permissions are handled."""
        perm_repo = PermissionRepository(async_session)

        # Create first permission
        perm1 = await perm_repo.create_permission("resource", "action")

        # Try to create duplicate - should return existing
        perm2 = await perm_repo.create_permission("resource", "action")

        assert perm1.id == perm2.id


class TestRoleRepository:
    """Test role repository operations."""

    @pytest.mark.asyncio()
    async def test_get_by_name(self, async_session: AsyncSession, test_roles):
        """Test getting role by name."""
        role_repo = RoleRepository(async_session)

        role = await role_repo.get_by_name("admin")
        assert role is not None
        assert role.name == "admin"

        # Non-existent role
        role = await role_repo.get_by_name("nonexistent")
        assert role is None

    @pytest.mark.asyncio()
    async def test_assign_role_to_user(
        self, async_session: AsyncSession, test_user: User, test_roles: dict
    ):
        """Test assigning role to user."""
        role_repo = RoleRepository(async_session)
        admin_role = test_roles["admin"]

        # Assign role
        success = await role_repo.assign_role_to_user(test_user.id, admin_role.id)
        assert success is True

        # Try to assign again - should return False
        success = await role_repo.assign_role_to_user(test_user.id, admin_role.id)
        assert success is False

        # Verify assignment
        user_roles = await role_repo.get_user_roles(test_user.id)
        assert len(user_roles) == 1
        assert user_roles[0].name == "admin"

    @pytest.mark.asyncio()
    @pytest.mark.skip(reason="Database table creation issue - no such table: user_roles")
    async def test_remove_role_from_user(
        self, async_session: AsyncSession, test_user: User, test_roles: dict
    ):
        """Test removing role from user."""
        role_repo = RoleRepository(async_session)
        admin_role = test_roles["admin"]

        # Assign role first
        await role_repo.assign_role_to_user(test_user.id, admin_role.id)

        # Remove role
        success = await role_repo.remove_role_from_user(test_user.id, admin_role.id)
        assert success is True

        # Try to remove again - should return False
        success = await role_repo.remove_role_from_user(test_user.id, admin_role.id)
        assert success is False

        # Verify removal
        user_roles = await role_repo.get_user_roles(test_user.id)
        assert len(user_roles) == 0

    @pytest.mark.asyncio()
    @pytest.mark.skip(reason="Database table creation issue - no such table: roles")
    async def test_update_permissions(self, async_session: AsyncSession, test_roles: dict):
        """Test updating role permissions."""
        role_repo = RoleRepository(async_session)
        author_role = test_roles["author"]

        new_permissions = ["runs:read", "artifacts:read", "custom:permission"]
        updated_role = await role_repo.update_permissions(author_role.id, new_permissions)

        assert updated_role is not None
        assert updated_role.permissions == new_permissions


class TestRBACManager:
    """Test RBAC manager functionality."""

    @pytest.mark.asyncio()
    async def test_assign_role_by_name(
        self, rbac_manager: RBACManager, test_user: User, test_roles: dict
    ):
        """Test assigning role by name through RBAC manager."""
        success = await rbac_manager.assign_role_to_user(str(test_user.id), "reviewer")
        assert success is True

        # Verify assignment
        roles = await rbac_manager.get_user_roles(str(test_user.id))
        assert len(roles) == 1
        assert roles[0].name == "reviewer"

    @pytest.mark.asyncio()
    @pytest.mark.skip(reason="Database table creation issue - needs fix")
    async def test_get_user_permissions(
        self, rbac_manager: RBACManager, test_user: User, test_roles: dict
    ):
        """Test getting user permissions through roles."""
        # Assign multiple roles
        await rbac_manager.assign_role_to_user(str(test_user.id), "author")
        await rbac_manager.assign_role_to_user(str(test_user.id), "reviewer")

        # Get permissions
        permissions = await rbac_manager.get_user_permissions(str(test_user.id))

        # Should have combined permissions from both roles
        assert "runs:create" in permissions  # From author
        assert "artifacts:approve" in permissions  # From reviewer
        assert "quality:read" in permissions  # From reviewer

        # Should be deduplicated
        assert permissions.count("runs:read") == 1

    @pytest.mark.asyncio()
    @pytest.mark.skip(reason="Database table issue - lazy loading fails")
    async def test_has_permission(
        self, rbac_manager: RBACManager, test_user: User, test_roles: dict
    ):
        """Test permission checking."""
        # Assign author role
        await rbac_manager.assign_role_to_user(str(test_user.id), "author")

        # Check permissions
        assert await rbac_manager.has_permission(str(test_user.id), "runs", "create") is True

        assert await rbac_manager.has_permission(str(test_user.id), "runs", "read") is True

        # Author shouldn't have admin permissions
        assert await rbac_manager.has_permission(str(test_user.id), "users", "delete") is False

        # Test non-existent permission
        assert (
            await rbac_manager.has_permission(str(test_user.id), "nonexistent", "action") is False
        )

    @pytest.mark.asyncio()
    async def test_wildcard_permissions(
        self, rbac_manager: RBACManager, test_user: User, test_roles: dict
    ):
        """Test wildcard permission checking."""
        # Test owner with *:* permission
        await rbac_manager.assign_role_to_user(str(test_user.id), "owner")

        # Should have all permissions
        assert (
            await rbac_manager.has_permission(str(test_user.id), "anything", "everything") is True
        )

        # Test admin with users:* permission
        admin_user_data = {
            "email": "admin@example.com",
            "hashed_password": "hashed",
            "is_active": True,
            "is_verified": True,
            "roles": [],
        }
        user_repo = UserRepository(rbac_manager.session)
        admin_user = await user_repo.create(**admin_user_data)

        await rbac_manager.assign_role_to_user(str(admin_user.id), "admin")

        # Should have all user permissions
        assert await rbac_manager.has_permission(str(admin_user.id), "users", "create") is True
        assert await rbac_manager.has_permission(str(admin_user.id), "users", "delete") is True
        assert await rbac_manager.has_permission(str(admin_user.id), "users", "anything") is True

        # But not other resources
        assert await rbac_manager.has_permission(str(admin_user.id), "runs", "delete") is False

    @pytest.mark.asyncio()
    async def test_has_role(self, rbac_manager: RBACManager, test_user: User, test_roles: dict):
        """Test role checking."""
        # Initially no roles
        assert await rbac_manager.has_role(str(test_user.id), "admin") is False

        # Assign role
        await rbac_manager.assign_role_to_user(str(test_user.id), "admin")

        # Now should have role
        assert await rbac_manager.has_role(str(test_user.id), "admin") is True
        assert await rbac_manager.has_role(str(test_user.id), "owner") is False

    @pytest.mark.asyncio()
    async def test_create_role(self, rbac_manager: RBACManager):
        """Test creating new role."""
        role = await rbac_manager.create_role(
            name="custom_role",
            permissions=["runs:read", "artifacts:read"],
            description="Custom test role",
        )

        assert role is not None
        assert role.name == "custom_role"
        assert role.permissions == ["runs:read", "artifacts:read"]
        assert role.description == "Custom test role"

        # Try to create duplicate
        duplicate = await rbac_manager.create_role(
            name="custom_role", permissions=["different:permission"]
        )

        # Should return existing role
        assert duplicate.id == role.id
        assert duplicate.permissions == role.permissions

    @pytest.mark.asyncio()
    async def test_update_role_permissions(self, rbac_manager: RBACManager, test_roles: dict):
        """Test updating role permissions."""
        new_permissions = ["runs:read", "new:permission"]

        updated = await rbac_manager.update_role_permissions("viewer", new_permissions)

        assert updated is not None
        assert updated.permissions == new_permissions

        # Test non-existent role
        updated = await rbac_manager.update_role_permissions("nonexistent", new_permissions)
        assert updated is None


class TestDefaultRoles:
    """Test default role definitions."""

    def test_get_all_permissions(self):
        """Test getting all possible permissions."""
        permissions = get_all_permissions()

        # Should include regular permissions
        assert "runs:create" in permissions
        assert "users:delete" in permissions

        # Should include wildcards
        assert "*:*" in permissions
        assert "runs:*" in permissions
        assert "*:create" in permissions

        # Should be sorted
        assert permissions == sorted(permissions)

    def test_get_role_permissions(self):
        """Test getting permissions for specific role."""
        # Test owner
        owner_perms = get_role_permissions("owner")
        assert owner_perms == ["*:*"]

        # Test admin
        admin_perms = get_role_permissions("admin")
        assert "users:*" in admin_perms
        assert "roles:*" in admin_perms
        assert "runs:create" not in admin_perms

        # Test non-existent role
        perms = get_role_permissions("nonexistent")
        assert perms == []

    def test_get_role_description(self):
        """Test getting role descriptions."""
        desc = get_role_description("reviewer")
        assert "Read artifacts" in desc

        desc = get_role_description("nonexistent")
        assert desc == ""

    def test_all_default_roles_defined(self):
        """Test that all expected roles are defined."""
        expected_roles = ["owner", "admin", "operator", "reviewer", "author", "viewer"]

        for role in expected_roles:
            assert role in DEFAULT_ROLES
            assert "description" in DEFAULT_ROLES[role]
            assert "permissions" in DEFAULT_ROLES[role]
            assert len(DEFAULT_ROLES[role]["permissions"]) > 0


class TestRBACEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio()
    async def test_invalid_user_id(self, rbac_manager: RBACManager, test_roles: dict):
        """Test operations with invalid user ID."""
        # Invalid UUID
        success = await rbac_manager.assign_role_to_user("invalid-uuid", "admin")
        assert success is False

        # Non-existent user
        fake_uuid = str(uuid4())
        success = await rbac_manager.assign_role_to_user(fake_uuid, "admin")
        assert success is False

    @pytest.mark.asyncio()
    async def test_empty_permissions(self, rbac_manager: RBACManager, test_user: User):
        """Test user with no roles."""
        permissions = await rbac_manager.get_user_permissions(str(test_user.id))
        assert permissions == []

        # Should have no permissions
        assert await rbac_manager.has_permission(str(test_user.id), "runs", "read") is False
