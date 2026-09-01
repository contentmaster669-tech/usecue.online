"""User lookup by API key hash."""

import logging

from callyr.auth.keys import hash_key
from callyr.db.client import get_client

log = logging.getLogger("callyr.users")


async def resolve_user_id(raw_key: str) -> str | None:
    """Map a raw API key to a user id, or None if unknown/revoked.

    Only the sha256 hash is stored, so the raw key is hashed and compared
    server-side; the plaintext key never touches the database.
    """
    if not raw_key:
        return None
    client = await get_client()
    if client is None:
        return None
    try:
        result = (
            await client.table("users")
            .select("id")
            .eq("api_key_hash", hash_key(raw_key))
            .eq("revoked", False)
            .limit(1)
            .execute()
        )
        if not result.data:
            return None
        return result.data[0]["id"]
    except Exception:
        log.exception("user lookup failed")
        return None
