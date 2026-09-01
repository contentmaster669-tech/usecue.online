"""Async Supabase client.

Connects with the SERVICE ROLE key. RLS is deny-by-default with no permissive
anon policies, so the service role is the only path to any row.
"""

import logging

from callyr import config
from supabase import AsyncClient, acreate_client

log = logging.getLogger("callyr.db")

_client: AsyncClient | None = None


async def get_client() -> AsyncClient | None:
    """Return a cached async client, or None if unconfigured/unreachable.

    Cached at module level: Vercel shares 1024 file descriptors across
    concurrent executions, so building a client per request leaks connections.
    """
    global _client
    if _client is not None:
        return _client
    if not (config.SUPABASE_URL and config.SUPABASE_SERVICE_KEY):
        log.error("Supabase not configured; SUPABASE_URL/SUPABASE_SERVICE_KEY missing")
        return None
    try:
        _client = await acreate_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
        return _client
    except Exception:
        log.exception("could not create Supabase client")
        return None
