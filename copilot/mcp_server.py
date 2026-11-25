"""Compatibility entry point for the stdio MCP server."""
import sys
from mcp_server import server

if __name__ == "__main__":
    server.server.run(transport="stdio")
else:
    sys.modules[__name__] = server
