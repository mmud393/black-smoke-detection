from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_ph = PasswordHasher()  # Argon2id by default
MIN_LENGTH = 12


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(hashed: str, pw: str) -> bool:
    try:
        return _ph.verify(hashed, pw)
    except (VerificationError, InvalidHashError):
        return False


def check_strength(pw: str) -> str | None:
    if len(pw) < MIN_LENGTH:
        return f"password must be at least {MIN_LENGTH} characters"
    if pw.lower() == pw or pw.upper() == pw or not any(c.isdigit() for c in pw):
        return "password must mix upper/lower case letters and digits"
    return None
