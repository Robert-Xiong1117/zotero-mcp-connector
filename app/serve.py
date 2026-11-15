"""Server child process: zotero-mcp-lite (with its OAuth) + optional AI4Paper proxy."""
import os
import sys

# Stateless HTTP: every request stands on its own. In the default stateful mode the MCP library
# answers any request without an Mcp-Session-Id header with HTTP 400 "Missing session ID", which
# is what the Claude PowerPoint add-in hit (claude.ai web keeps the header, so it never showed there).
# Session ids also die on every server restart; stateless mode has none to lose. Tools here keep no
# per-session state, so nothing is given up.
HTTP_RUN_OPTIONS = {"stateless_http": True}


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
    try:
        from .annotations import install
        install()       # annotations from the live library via the local API, not a (possibly stale) zotero.sqlite
        print("  Annotations: read via Zotero local API", file=sys.stderr)
    except Exception as e:
        print(f"  Annotations: local API reader disabled ({type(e).__name__}: {e})", file=sys.stderr)
    try:
        from .bridge import register
        register(mcp)   # tools report plugin/Zotero problems themselves; registration never needs Zotero
        print("  Zotero bridge tools: zotero_highlight_quote, zotero_find_pdf", file=sys.stderr)
    except Exception as e:
        print(f"  Zotero bridge tools: disabled ({type(e).__name__}: {e})", file=sys.stderr)
    print("  HTTP: stateless (no Mcp-Session-Id required)", file=sys.stderr)
    mcp.run(transport="streamable-http", host="127.0.0.1", port=port, **HTTP_RUN_OPTIONS)
