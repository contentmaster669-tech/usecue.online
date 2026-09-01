"""ASGI middleware: key extraction and GET-block.

Wraps the FastMCP app. Two jobs:

1. Pull the API key out of the URL path (/mcp/<key>) and stash it in a
   ContextVar for the tools, then rewrite the path to /mcp so FastMCP routes
   normally.

2. Reject GET on the MCP path. FastMCP's stateless mode still accepts GET and
   opens a long-lived SSE stream instead of returning 405
   (https://github.com/PrefectHQ/fastmcp/issues/3179). On serverless that is a
   function hanging on the billing clock.
"""

import logging

from callyr.auth.context import set_api_key

log = logging.getLogger("callyr.auth")

MCP_PATH = "/mcp"


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

            # /mcp/<key> -> key, and route the request as plain /mcp.
            suffix = path[len(MCP_PATH) :].strip("/")
            set_api_key(suffix)
            scope = dict(scope)
            scope["path"] = MCP_PATH
            scope["raw_path"] = MCP_PATH.encode("utf-8")

        await self.app(scope, receive, send)
