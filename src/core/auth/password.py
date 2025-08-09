"""Password hashing and validation utilities."""

import re
import secrets
import string
from typing import Tuple

from passlib.context import CryptContext

# Create password context with bcrypt
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password

    Returns:
        Hashed password
    """
    return str(pwd_context.hash(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify
        hashed_password: Hashed password to check against

    Returns:
        True if password matches, False otherwise
    """
    return bool(pwd_context.verify(plain_password, hashed_password))


def generate_reset_token(length: int = 32) -> str:
    """Generate a secure random reset token.

    Args:
        length: Length of the token

    Returns:
        Secure random token
    """
    # Use URL-safe characters
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def is_strong_password(password: str) -> Tuple[bool, str]:
    """Check if a password meets strength requirements.

    Requirements:
    - At least 8 characters long
    - Contains at least one uppercase letter
    - Contains at least one lowercase letter
    - Contains at least one digit
    - Contains at least one special character

    Args:
        password: Password to check

    Returns:
        Tuple of (is_strong, message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"\d", password):
        return False, "Password must contain at least one digit"

    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?]", password):
        return False, "Password must contain at least one special character"

    return True, "Password is strong"


def generate_secure_password(length: int = 16) -> str:
    """Generate a secure random password.

    Args:
        length: Length of the password (minimum 8)

    Returns:
        Secure random password that meets strength requirements
    """
    if length < 8:
        length = 8

    # Ensure password has required character types
    password_chars = []

    # Add at least one of each required type
    password_chars.append(secrets.choice(string.ascii_uppercase))
    password_chars.append(secrets.choice(string.ascii_lowercase))
    password_chars.append(secrets.choice(string.digits))
    password_chars.append(secrets.choice("!@#$%^&*()_+-=[]{}|"))

    # Fill the rest with random characters from all categories
    all_chars = (
        string.ascii_uppercase + string.ascii_lowercase + string.digits + "!@#$%^&*()_+-=[]{}|"
    )

    for _ in range(length - 4):
        password_chars.append(secrets.choice(all_chars))

    # Shuffle to avoid predictable patterns
    secrets.SystemRandom().shuffle(password_chars)

    return "".join(password_chars)
