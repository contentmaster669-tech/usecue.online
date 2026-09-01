"""Cue MCP server. Vercel loads the ASGI `app` exported here.

Stateless HTTP is mandatory, not a preference: serverless has no session
affinity, so MCP sessions cannot survive across invocations.
"""

import logging

from fastmcp import FastMCP

from callyr import config
from callyr.auth.middleware import AuthMiddleware
from callyr.tools import analyze, status, usage_tool

logging.basicConfig(level=logging.INFO)

mcp = FastMCP(
    name=config.SERVER_NAME,
    version=config.SERVER_VERSION,
    instructions=config.SERVER_INSTRUCTIONS,
)

# Tool registration order is the order clients display them in.
status.register(mcp)  # the Active Indicator, listed first
analyze.register(mcp)
usage_tool.register(mcp)

app = AuthMiddleware(mcp.http_app(stateless_http=True, path="/mcp"))
