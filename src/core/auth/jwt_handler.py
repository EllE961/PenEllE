"""JWT token handling for authentication."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from jose import JWTError, jwt

from src.core.config import settings

logger = logging.getLogger(__name__)


class TokenError(Exception):
    """Raised when token operations fail."""

    pass


class JWTHandler:
    """Handles JWT token creation and validation."""

    def __init__(self, secret_key: Optional[str] = None, algorithm: Optional[str] = None):
        """Initialize JWT handler.

        Args:
            secret_key: Secret key for signing tokens
            algorithm: Algorithm to use for signing
        """
        self.secret_key = secret_key or settings.SECRET_KEY
        self.algorithm = algorithm or settings.ALGORITHM

    def create_access_token(
        self, data: Dict[str, Any], expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create an access token.

        Args:
            data: Data to encode in the token
            expires_delta: Custom expiration time

        Returns:
            Encoded JWT token
        """
        to_encode = data.copy()

        # Set expiration
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
            )

        # Add standard claims
        to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "access"})

        # Ensure UUID fields are strings
        if "user_id" in to_encode and isinstance(to_encode["user_id"], UUID):
            to_encode["user_id"] = str(to_encode["user_id"])

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

        return str(encoded_jwt)

    def create_refresh_token(self, data: Dict[str, Any]) -> str:
        """Create a refresh token.

        Args:
            data: Data to encode in the token

        Returns:
            Encoded JWT refresh token
        """
        to_encode = data.copy()

        # Set longer expiration for refresh token
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        # Add standard claims
        to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc), "type": "refresh"})

        # Ensure UUID fields are strings
        if "user_id" in to_encode and isinstance(to_encode["user_id"], UUID):
            to_encode["user_id"] = str(to_encode["user_id"])

        encoded_jwt = jwt.encode(to_encode, self.secret_key, algorithm=self.algorithm)

        return str(encoded_jwt)

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify and decode a token.

        Args:
            token: JWT token to verify

        Returns:
            Decoded token payload

        Raises:
            TokenError: If token is invalid or expired
        """
        try:
            payload: Dict[str, Any] = jwt.decode(
                token, self.secret_key, algorithms=[self.algorithm]
            )
            return payload
        except JWTError as e:
            logger.warning(f"Token verification failed: {e}")
            raise TokenError(f"Invalid token: {e}")

    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode a token without verification.

        Args:
            token: JWT token to decode

        Returns:
            Decoded token payload

        Note:
            This does NOT verify the token signature.
            Use verify_token for secure operations.
        """
        try:
            # Decode without verification
            payload: Dict[str, Any] = jwt.get_unverified_claims(token)
            return payload
        except JWTError as e:
            logger.warning(f"Token decode failed: {e}")
            raise TokenError(f"Invalid token format: {e}")

    def get_current_user(self, token: str) -> Dict[str, Any]:
        """Get current user info from token.

        Args:
            token: JWT access token

        Returns:
            User information from token

        Raises:
            TokenError: If token is invalid or not an access token
        """
        payload = self.verify_token(token)

        # Verify it's an access token
        if payload.get("type") != "access":
            raise TokenError("Token is not an access token")

        # Extract user info
        user_info = {
            "user_id": payload.get("user_id"),
            "email": payload.get("email"),
            "roles": payload.get("roles", []),
        }

        # Ensure required fields
        if not user_info["user_id"] or not user_info["email"]:
            raise TokenError("Token missing required user information")

        return user_info

    def refresh_access_token(self, refresh_token: str) -> str:
        """Create new access token from refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            New access token

        Raises:
            TokenError: If refresh token is invalid
        """
        payload = self.verify_token(refresh_token)

        # Verify it's a refresh token
        if payload.get("type") != "refresh":
            raise TokenError("Token is not a refresh token")

        # Create new access token with same user data
        user_data = {
            "user_id": payload.get("user_id"),
            "email": payload.get("email"),
            "roles": payload.get("roles", []),
        }

        return self.create_access_token(user_data)


# Global JWT handler instance
jwt_handler = JWTHandler()
