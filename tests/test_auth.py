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


class TestLandingPage:
    """Non-/mcp paths serve the landing page; /mcp keeps working."""

    async def test_root_serves_html(self):
        downstream = _Recorder()
        sent = await _run(
            AuthMiddleware(downstream),
            {"type": "http", "method": "GET", "path": "/"},
        )
        assert sent[0]["status"] == 200
        headers = dict(sent[0]["headers"])
        assert b"text/html" in headers[b"content-type"]
        assert b"<title>Cue</title>" in sent[1]["body"]
        assert downstream.scope is None  # never reached FastMCP

    async def test_arbitrary_path_serves_html(self):
        downstream = _Recorder()
        sent = await _run(
            AuthMiddleware(downstream),
            {"type": "http", "method": "GET", "path": "/pricing"},
        )
        assert sent[0]["status"] == 200

    async def test_head_returns_headers_without_body(self):
        downstream = _Recorder()
        sent = await _run(
            AuthMiddleware(downstream),
            {"type": "http", "method": "HEAD", "path": "/"},
        )
        assert sent[0]["status"] == 200
        assert sent[1]["body"] == b""

    async def test_post_to_non_mcp_path_is_404(self):
        # A marketing page should not answer POSTs with HTML.
        downstream = _Recorder()
        sent = await _run(
            AuthMiddleware(downstream),
            {"type": "http", "method": "POST", "path": "/"},
        )
        assert sent[0]["status"] == 404

    async def test_mcp_post_still_reaches_fastmcp(self):
        """The landing page must not shadow the MCP route."""
        downstream = _Recorder()
        await _run(
            AuthMiddleware(downstream),
            {"type": "http", "method": "POST", "path": "/mcp"},
        )
        assert downstream.scope is not None

    async def test_mcp_get_still_405_not_landing_page(self):
        """/mcp GET must stay 405 -- it must NOT fall through to the page."""
        downstream = _Recorder()
        sent = await _run(
            AuthMiddleware(downstream),
            {"type": "http", "method": "GET", "path": "/mcp"},
        )
        assert sent[0]["status"] == 405

    async def test_keyed_mcp_path_still_routes(self):
        from callyr.auth.context import get_api_key

        downstream = _Recorder()
        await _run(
            AuthMiddleware(downstream),
            {"type": "http", "method": "POST", "path": "/mcp/abc123"},
        )
        assert downstream.scope["path"] == "/mcp"
        assert get_api_key() == "abc123"


class TestHeaderAuth:
    """The key travels in a header so it stays out of URLs, which leak into
    browser history, proxy logs, and anything a user pastes for help."""

    async def test_authorization_bearer(self):
        from callyr.auth.context import get_api_key

        downstream = _Recorder()
        await _run(
            AuthMiddleware(downstream),
            {
                "type": "http",
                "method": "POST",
                "path": "/mcp",
                "headers": [(b"authorization", b"Bearer hdr-key-1")],
            },
        )
        assert get_api_key() == "hdr-key-1"

    async def test_authorization_bare_key(self):
        # A user pasting into a header field will not always add "Bearer".
        from callyr.auth.context import get_api_key

        downstream = _Recorder()
        await _run(
            AuthMiddleware(downstream),
            {
                "type": "http",
                "method": "POST",
                "path": "/mcp",
                "headers": [(b"authorization", b"bare-key-2")],
            },
        )
        assert get_api_key() == "bare-key-2"

    async def test_x_cue_key_header(self):
        from callyr.auth.context import get_api_key

        downstream = _Recorder()
        await _run(
            AuthMiddleware(downstream),
            {
                "type": "http",
                "method": "POST",
                "path": "/mcp",
                "headers": [(b"x-cue-key", b"custom-key-3")],
            },
        )
        assert get_api_key() == "custom-key-3"

    async def test_header_wins_over_path(self):
        from callyr.auth.context import get_api_key

        downstream = _Recorder()
        await _run(
            AuthMiddleware(downstream),
            {
                "type": "http",
                "method": "POST",
                "path": "/mcp/path-key",
                "headers": [(b"authorization", b"Bearer header-key")],
            },
        )
        assert get_api_key() == "header-key"

    async def test_path_still_works_without_a_header(self):
        """Already-connected clients must not break."""
        from callyr.auth.context import get_api_key

        downstream = _Recorder()
        await _run(
            AuthMiddleware(downstream),
            {"type": "http", "method": "POST", "path": "/mcp/legacy-key", "headers": []},
        )
        assert get_api_key() == "legacy-key"

    async def test_no_key_anywhere_is_empty(self):
        from callyr.auth.context import get_api_key

        downstream = _Recorder()
        await _run(
            AuthMiddleware(downstream),
            {"type": "http", "method": "POST", "path": "/mcp", "headers": []},
        )
        assert get_api_key() == ""
