"""ASGI middleware: landing page, key extraction, and GET-block.

Wraps the FastMCP app. Three jobs:

1. Serve the static landing page on every non-/mcp path. Routing lives here
   rather than in vercel.json rewrites so that one place owns the decision --
   a declarative rewrite plus a catch-all function can silently disagree
   about which owns a path, and that failure is invisible until production.

2. Pull the API key out of the URL path (/mcp/<key>) and stash it in a
   ContextVar for the tools, then rewrite the path to /mcp so FastMCP routes
   normally.

3. Reject GET on the MCP path. FastMCP's stateless mode still accepts GET and
   opens a long-lived SSE stream instead of returning 405
   (https://github.com/PrefectHQ/fastmcp/issues/3179). On serverless that is a
   function hanging on the billing clock.
"""

import logging
from pathlib import Path

from callyr.auth.context import set_api_key

log = logging.getLogger("callyr.auth")

MCP_PATH = "/mcp"

# site/index.html, relative to the repo root (callyr/auth/ -> ../..).
_SITE_INDEX = Path(__file__).resolve().parents[2] / "site" / "index.html"

# Read once at cold start, not per request: the page is static and a
# serverless container serves many requests.
_PAGE: bytes | None = None


def _landing_page() -> bytes | None:
    """The landing page bytes, or None if it is not in the bundle."""
    global _PAGE
    if _PAGE is None:
        try:
            _PAGE = _SITE_INDEX.read_bytes()
        except OSError:
            log.warning("landing page not found at %s", _SITE_INDEX)
            return None
    return _PAGE


def _key_from_headers(scope) -> str:
    """Extract the API key from request headers.

    Accepts either:
        Authorization: Bearer <key>
        X-Cue-Key: <key>

    Returns "" when neither is present, so the caller can fall back to the
    path form. ASGI header names are always lowercase bytes.
    """
    headers = dict(scope.get("headers") or [])

    raw = headers.get(b"authorization", b"").decode("latin-1").strip()
    if raw:
        # "Bearer <key>" is the conventional form, but accept a bare key too --
        # a user pasting into a header field will not always add the prefix.
        parts = raw.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
        return raw

    return headers.get(b"x-cue-key", b"").decode("latin-1").strip()


async def _send_page(send, body: bytes, status: int = 200) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"text/html; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
                # Short cache: the page is static, but a redeploy should reach
                # visitors quickly rather than sit in a CDN for a day.
                (b"cache-control", b"public, max-age=300"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _send_404(send) -> None:
    body = b"Not Found"
    await send(
        {
            "type": "http.response.start",
            "status": 404,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def _send_405(send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 405,
            "headers": [
                (b"content-type", b"text/plain; charset=utf-8"),
                (b"allow", b"POST"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": b"Method Not Allowed"})


class AuthMiddleware:
    """Pure-ASGI wrapper around the FastMCP app."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")

        if path == MCP_PATH or path.startswith(MCP_PATH + "/"):
            # Block GET before it can open an SSE stream and hang the function.
            if scope.get("method") == "GET":
                await _send_405(send)
                return

            # Header first, path as fallback. A header keeps the key out of
            # URLs, which otherwise leak into browser history, proxy logs, and
            # anything a user pastes when asking for help. The path form still
            # works so already-connected clients do not break.
            suffix = path[len(MCP_PATH) :].strip("/")
            set_api_key(_key_from_headers(scope) or suffix)
            scope = dict(scope)
            scope["path"] = MCP_PATH
            scope["raw_path"] = MCP_PATH.encode("utf-8")

            await self.app(scope, receive, send)
            return

        # Everything outside /mcp is the landing page. GET/HEAD only -- a POST
        # to a marketing page is not something to answer with HTML.
        if scope.get("method") in ("GET", "HEAD"):
            page = _landing_page()
            if page is not None:
                await _send_page(send, b"" if scope["method"] == "HEAD" else page)
                return

        await _send_404(send)
