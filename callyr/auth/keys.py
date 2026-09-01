"""API key hashing and generation.

Keys are path-based: https://<host>/mcp/<key>. Only the sha256 hash is stored;
the raw key is shown once at issuance and never persisted.
"""

import hashlib
import hmac
import secrets

KEY_BYTES = 32
PREFIX_LEN = 8


def generate_key() -> str:
    """Mint a new raw API key. Show once, store only its hash."""
    return secrets.token_urlsafe(KEY_BYTES)


def hash_key(raw_key: str) -> str:
    """sha256 of the raw key, hex-encoded."""
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def key_prefix(raw_key: str) -> str:
    """First few chars, for display and support lookups."""
    return raw_key[:PREFIX_LEN]


def keys_match(raw_key: str, stored_hash: str) -> bool:
    """Constant-time comparison, to avoid leaking the hash via timing."""
    return hmac.compare_digest(hash_key(raw_key), stored_hash)
