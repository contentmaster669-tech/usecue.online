"""Request-scoped API key.

Stateless HTTP means there is no session to hang identity on, so the key is
carried per-request in a ContextVar that the middleware sets and the tools
read. ContextVar is task-local, so concurrent requests cannot see each other's
key even though the module is shared.
"""

from contextvars import ContextVar

_api_key: ContextVar[str] = ContextVar("callyr_api_key", default="")


def set_api_key(raw_key: str) -> None:
    """Called by the middleware once per request."""
    _api_key.set(raw_key)


def get_api_key() -> str:
    """Raw key for the in-flight request, or "" if none was supplied."""
    return _api_key.get()
