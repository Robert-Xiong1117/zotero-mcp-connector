"""Server child process: zotero-mcp-lite (with its OAuth) + optional AI4Paper proxy."""
import os
import sys


def serve(port: int) -> None:
    from zotero_mcp import cli
    cli.setup_environment()
    from zotero_mcp.server import mcp
    try:
        cli._configure_http_auth(mcp, public_url=os.environ.get("ZOTERO_MCP_PUBLIC_URL"), no_auth=False)
    except cli.RemoteAuthConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(2)
    try:
        from .ai4paper import mount_from_env
        if mount_from_env(mcp):
            print("  AI4Paper proxy: mounted (namespace ai4paper)", file=sys.stderr)
    except Exception as e:  # never let the optional proxy take the main server down
        print(f"  AI4Paper proxy: disabled ({type(e).__name__}: {e})", file=sys.stderr)
    mcp.run(transport="streamable-http", host="127.0.0.1", port=port)
