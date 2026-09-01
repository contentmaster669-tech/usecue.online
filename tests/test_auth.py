"""Key handling and the middleware's two jobs."""

from callyr.auth.keys import generate_key, hash_key, key_prefix, keys_match
from callyr.auth.middleware import AuthMiddleware


class TestKeys:
    def test_keys_are_unique(self):
        assert generate_key() != generate_key()

    def test_hash_is_stable_and_not_the_key(self):
        raw = generate_key()
        assert hash_key(raw) == hash_key(raw)
        assert raw not in hash_key(raw)

    def test_match_accepts_correct_and_rejects_wrong(self):
        raw = generate_key()
        assert keys_match(raw, hash_key(raw))
        assert not keys_match(generate_key(), hash_key(raw))

    def test_prefix_is_short_and_from_the_key(self):
        raw = generate_key()
        assert len(key_prefix(raw)) == 8
        assert raw.startswith(key_prefix(raw))


class _Recorder:
    """Minimal downstream ASGI app that records what it was handed."""

    def __init__(self):
        self.scope = None

    async def __call__(self, scope, receive, send):
        self.scope = scope


async def _run(app, scope):
    sent = []

    async def receive():
        return {"type": "http.request"}

    async def send(msg):
        sent.append(msg)

    await app(scope, receive, send)
    return sent


class TestMiddleware:
    async def test_get_is_blocked_with_405(self):
        """FastMCP stateless still opens SSE on GET; on serverless that hangs
        the function on the billing clock."""
        downstream = _Recorder()
        sent = await _run(
            AuthMiddleware(downstream),
            {"type": "http", "method": "GET", "path": "/mcp"},
        )
        assert sent[0]["status"] == 405
        assert downstream.scope is None  # never reached FastMCP

    async def test_post_passes_through(self):
        downstream = _Recorder()
        await _run(
            AuthMiddleware(downstream),
            {"type": "http", "method": "POST", "path": "/mcp"},
        )
        assert downstream.scope is not None

    async def test_key_is_stripped_from_path(self):
        from callyr.auth.context import get_api_key

        downstream = _Recorder()
        await _run(
            AuthMiddleware(downstream),
            {"type": "http", "method": "POST", "path": "/mcp/secret-key-123"},
        )
        # FastMCP must see a clean /mcp, not the key-bearing path.
        assert downstream.scope["path"] == "/mcp"
        assert get_api_key() == "secret-key-123"

    async def test_non_http_scope_passes_untouched(self):
        downstream = _Recorder()
        await _run(AuthMiddleware(downstream), {"type": "lifespan"})
        assert downstream.scope["type"] == "lifespan"
