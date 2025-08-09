"""Tests for authentication components."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt

from src.core.auth import (
    JWTHandler,
    TokenError,
    generate_reset_token,
    generate_secure_password,
    get_current_active_user,
    get_current_user,
    hash_password,
    is_strong_password,
    jwt_handler,
    verify_password,
)
from src.core.config import settings
from src.core.database.models import User


class TestPasswordUtilities:
    """Test password hashing and validation."""

    def test_hash_password(self):
        """Test password hashing."""
        password = "TestPassword123!"
        hashed = hash_password(password)

        # Hash should be different from original
        assert hashed != password
        # Should be a bcrypt hash
        assert hashed.startswith("$2b$")

    def test_verify_password(self):
        """Test password verification."""
        password = "TestPassword123!"
        hashed = hash_password(password)

        # Correct password should verify
        assert verify_password(password, hashed) is True

        # Wrong password should not verify
        assert verify_password("WrongPassword", hashed) is False

    def test_generate_reset_token(self):
        """Test reset token generation."""
        token1 = generate_reset_token()
        token2 = generate_reset_token()

        # Should be 32 characters by default
        assert len(token1) == 32
        # Should be different each time
        assert token1 != token2
        # Should only contain URL-safe characters
        assert all(c.isalnum() or c in "-_" for c in token1)

        # Test custom length
        token3 = generate_reset_token(length=16)
        assert len(token3) == 16

    def test_is_strong_password(self):
        """Test password strength validation."""
        # Too short
        is_strong, msg = is_strong_password("Short1!")
        assert is_strong is False
        assert "at least 8 characters" in msg

        # Missing uppercase
        is_strong, msg = is_strong_password("lowercase123!")
        assert is_strong is False
        assert "uppercase letter" in msg

        # Missing lowercase
        is_strong, msg = is_strong_password("UPPERCASE123!")
        assert is_strong is False
        assert "lowercase letter" in msg

        # Missing digit
        is_strong, msg = is_strong_password("NoDigits!ABC")
        assert is_strong is False
        assert "digit" in msg

        # Missing special character
        is_strong, msg = is_strong_password("NoSpecial123ABC")
        assert is_strong is False
        assert "special character" in msg

        # Strong password
        is_strong, msg = is_strong_password("StrongP@ssw0rd")
        assert is_strong is True
        assert "strong" in msg.lower()

    def test_generate_secure_password(self):
        """Test secure password generation."""
        password = generate_secure_password()

        # Should be 16 characters by default
        assert len(password) == 16

        # Should meet strength requirements
        is_strong, _ = is_strong_password(password)
        assert is_strong is True

        # Test custom length
        password2 = generate_secure_password(length=20)
        assert len(password2) == 20
        is_strong, _ = is_strong_password(password2)
        assert is_strong is True

        # Test minimum length enforcement
        password3 = generate_secure_password(length=5)
        assert len(password3) == 8  # Should be minimum 8


class TestJWTHandler:
    """Test JWT token handling."""

    @pytest.fixture()
    def handler(self):
        """Create JWT handler instance."""
        return JWTHandler(secret_key="test-secret-key", algorithm="HS256")

    @pytest.fixture()
    def user_data(self):
        """Sample user data for tokens."""
        return {
            "user_id": str(uuid4()),
            "email": "test@example.com",
            "roles": ["researcher"],
        }

    def test_create_access_token(self, handler, user_data):
        """Test access token creation."""
        token = handler.create_access_token(user_data)

        # Decode and verify
        payload = jwt.decode(token, handler.secret_key, algorithms=[handler.algorithm])

        assert payload["user_id"] == user_data["user_id"]
        assert payload["email"] == user_data["email"]
        assert payload["roles"] == user_data["roles"]
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_create_access_token_custom_expiry(self, handler, user_data):
        """Test access token with custom expiry."""
        expires_delta = timedelta(hours=1)
        token = handler.create_access_token(user_data, expires_delta)

        payload = jwt.decode(token, handler.secret_key, algorithms=[handler.algorithm])

        # Check expiry is approximately 1 hour from now
        exp_time = datetime.fromtimestamp(payload["exp"], tz=UTC)
        expected_exp = datetime.now(UTC) + expires_delta
        assert abs((exp_time - expected_exp).total_seconds()) < 5

    def test_create_refresh_token(self, handler, user_data):
        """Test refresh token creation."""
        token = handler.create_refresh_token(user_data)

        # Decode and verify
        payload = jwt.decode(token, handler.secret_key, algorithms=[handler.algorithm])

        assert payload["user_id"] == user_data["user_id"]
        assert payload["email"] == user_data["email"]
        assert payload["roles"] == user_data["roles"]
        assert payload["type"] == "refresh"
        assert "exp" in payload
        assert "iat" in payload

    def test_verify_token(self, handler, user_data):
        """Test token verification."""
        token = handler.create_access_token(user_data)

        # Verify valid token
        payload = handler.verify_token(token)
        assert payload["user_id"] == user_data["user_id"]

        # Test invalid token
        with pytest.raises(TokenError):
            handler.verify_token("invalid.token.here")

        # Test token with wrong signature
        wrong_handler = JWTHandler(secret_key="wrong-key", algorithm="HS256")
        with pytest.raises(TokenError):
            wrong_handler.verify_token(token)

    def test_verify_expired_token(self, handler, user_data):
        """Test expired token verification."""
        # Create token that's already expired
        token = handler.create_access_token(user_data, expires_delta=timedelta(seconds=-10))

        with pytest.raises(TokenError, match="Invalid token"):
            handler.verify_token(token)

    def test_decode_token(self, handler, user_data):
        """Test token decoding without verification."""
        token = handler.create_access_token(user_data)

        # Decode without verification
        payload = handler.decode_token(token)
        assert payload["user_id"] == user_data["user_id"]

        # Even works with wrong secret
        wrong_handler = JWTHandler(secret_key="wrong-key", algorithm="HS256")
        payload = wrong_handler.decode_token(token)
        assert payload["user_id"] == user_data["user_id"]

        # But fails on malformed token
        with pytest.raises(TokenError):
            handler.decode_token("not.a.token")

    def test_get_current_user(self, handler, user_data):
        """Test getting current user from token."""
        token = handler.create_access_token(user_data)

        # Get user info
        user_info = handler.get_current_user(token)
        assert user_info["user_id"] == user_data["user_id"]
        assert user_info["email"] == user_data["email"]
        assert user_info["roles"] == user_data["roles"]

        # Test with refresh token (should fail)
        refresh_token = handler.create_refresh_token(user_data)
        with pytest.raises(TokenError, match="not an access token"):
            handler.get_current_user(refresh_token)

        # Test with missing user info
        incomplete_data = {"user_id": str(uuid4())}  # Missing email
        token = handler.create_access_token(incomplete_data)
        with pytest.raises(TokenError, match="missing required"):
            handler.get_current_user(token)

    def test_refresh_access_token(self, handler, user_data):
        """Test refreshing access token."""
        refresh_token = handler.create_refresh_token(user_data)

        # Create new access token
        new_token = handler.refresh_access_token(refresh_token)

        # Verify new token
        payload = handler.verify_token(new_token)
        assert payload["user_id"] == user_data["user_id"]
        assert payload["email"] == user_data["email"]
        assert payload["type"] == "access"

        # Test with access token (should fail)
        access_token = handler.create_access_token(user_data)
        with pytest.raises(TokenError, match="not a refresh token"):
            handler.refresh_access_token(access_token)

    def test_uuid_handling(self, handler):
        """Test UUID conversion in tokens."""
        user_id = uuid4()  # UUID object
        data = {"user_id": user_id, "email": "test@example.com", "roles": []}

        token = handler.create_access_token(data)
        payload = handler.verify_token(token)

        # Should be converted to string
        assert payload["user_id"] == str(user_id)


class TestAuthDependencies:
    """Test FastAPI authentication dependencies."""

    @pytest.fixture()
    def mock_session(self):
        """Create mock database session."""
        return AsyncMock()

    @pytest.fixture()
    def mock_user(self):
        """Create mock user."""
        user = MagicMock(spec=User)
        user.id = uuid4()
        user.email = "test@example.com"
        user.is_active = True
        user.is_verified = True
        user.roles = ["researcher"]
        return user

    @pytest.fixture()
    def mock_credentials(self):
        """Create mock HTTP credentials."""
        creds = MagicMock()
        creds.credentials = "test-token"
        return creds

    @pytest.mark.asyncio()
    async def test_get_current_user(self, mock_session, mock_user, mock_credentials):
        """Test getting current user from token."""
        user_data = {
            "user_id": str(mock_user.id),
            "email": mock_user.email,
            "roles": mock_user.roles,
        }

        # Mock JWT handler
        with patch("src.core.auth.dependencies.jwt_handler.get_current_user") as mock_jwt:
            mock_jwt.return_value = user_data

            # Mock user repository
            with patch("src.core.auth.dependencies.UserRepository") as mock_repo_class:
                mock_repo = AsyncMock()
                mock_repo.get_by_id.return_value = mock_user
                mock_repo_class.return_value = mock_repo

                # Get current user
                user = await get_current_user(mock_credentials, mock_session)

                assert user == mock_user
                mock_jwt.assert_called_once_with("test-token")
                mock_repo.get_by_id.assert_called_once_with(str(mock_user.id))

    @pytest.mark.asyncio()
    async def test_get_current_user_not_found(self, mock_session, mock_credentials):
        """Test getting current user when user not found."""
        user_data = {
            "user_id": str(uuid4()),
            "email": "test@example.com",
            "roles": [],
        }

        with patch("src.core.auth.dependencies.jwt_handler.get_current_user") as mock_jwt:
            mock_jwt.return_value = user_data

            with patch("src.core.auth.dependencies.UserRepository") as mock_repo_class:
                mock_repo = AsyncMock()
                mock_repo.get_by_id.return_value = None  # User not found
                mock_repo_class.return_value = mock_repo

                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(mock_credentials, mock_session)

                assert exc_info.value.status_code == 401
                # The general exception handler catches this as "Could not validate credentials"
                assert "Could not validate credentials" in str(exc_info.value.detail)

    @pytest.mark.asyncio()
    async def test_get_current_user_invalid_token(self, mock_session, mock_credentials):
        """Test getting current user with invalid token."""
        with patch("src.core.auth.dependencies.jwt_handler.get_current_user") as mock_jwt:
            mock_jwt.side_effect = TokenError("Invalid token")

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_credentials, mock_session)

            assert exc_info.value.status_code == 401
            assert "Invalid token" in str(exc_info.value.detail)

    @pytest.mark.asyncio()
    async def test_get_current_active_user(self, mock_user):
        """Test getting current active user."""
        # Active user should pass
        user = await get_current_active_user(mock_user)
        assert user == mock_user

        # Inactive user should fail
        mock_user.is_active = False
        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(mock_user)

        assert exc_info.value.status_code == 403
        assert "Inactive user" in str(exc_info.value.detail)

    @pytest.mark.asyncio()
    async def test_require_roles(self, mock_user):
        """Test role requirement dependency."""
        from src.core.auth.dependencies import require_roles

        # Create role checker
        role_checker = require_roles(["researcher", "admin"])

        # User with required role should pass
        user = await role_checker(mock_user)
        assert user == mock_user

        # User without required role should fail
        mock_user.roles = ["viewer"]
        with pytest.raises(HTTPException) as exc_info:
            await role_checker(mock_user)

        assert exc_info.value.status_code == 403
        assert "lacks required roles" in str(exc_info.value.detail)

        # User with no roles should fail
        mock_user.roles = []
        with pytest.raises(HTTPException) as exc_info:
            await role_checker(mock_user)

        assert exc_info.value.status_code == 403

    def test_require_verified_user(self, mock_user):
        """Test verified user requirement."""
        from src.core.auth.dependencies import require_verified_user

        # Verified user should pass
        user = require_verified_user(mock_user)
        assert user == mock_user

        # Unverified user should fail
        mock_user.is_verified = False
        with pytest.raises(HTTPException) as exc_info:
            require_verified_user(mock_user)

        assert exc_info.value.status_code == 403
        assert "verification required" in str(exc_info.value.detail)


class TestGlobalInstances:
    """Test global authentication instances."""

    def test_jwt_handler_instance(self):
        """Test global JWT handler instance."""
        # Should use settings by default
        assert jwt_handler.secret_key == settings.SECRET_KEY
        assert jwt_handler.algorithm == settings.ALGORITHM

        # Should be able to create tokens
        token = jwt_handler.create_access_token(
            {"user_id": str(uuid4()), "email": "test@example.com", "roles": []}
        )
        assert isinstance(token, str)
