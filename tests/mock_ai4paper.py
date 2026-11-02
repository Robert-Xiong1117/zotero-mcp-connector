"""Stand-in for AI4Paper's local MCP endpoint: bearer-token protected, a few tools."""
import sys

from fastmcp import FastMCP
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

TOKEN = "a4p-mcp-test"
mcp = FastMCP("ai4paper-mock",
              auth=StaticTokenVerifier(tokens={TOKEN: {"client_id": "t", "scopes": []}}))


@mcp.tool
def zotero_search_items(query: str) -> str:
    return f"found:{query}"


@mcp.tool
def zotero_add_tag(item_key: str, tag: str) -> str:
    return f"tagged:{item_key}:{tag}"


@mcp.tool
def zotero_delete_tags_from_library(tag: str) -> str:
    return "DELETED"


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=int(sys.argv[1]), path="/ai4paper/mcp")
