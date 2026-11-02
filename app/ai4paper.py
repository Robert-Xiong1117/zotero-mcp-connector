"""Optional proxy of the local AI4Paper MCP server (Zotero plugin) into the connector.

AI4Paper listens only on 127.0.0.1 with its own token, which claude.ai connectors cannot use.
We mount it inside our OAuth-protected server under the namespace "ai4paper", forwarding
locally with the token, and expose only an allow-list of tools.
"""
import asyncio
import os

DEFAULT_URL = "http://127.0.0.1:23119/ai4paper/mcp"
NAMESPACE = "ai4paper"

# Allow-list enabled by default (read + import/organize). Everything else stays hidden.
DEFAULT_TOOLS = [
    # read
    "zotero_search_items", "zotero_semantic_search", "zotero_semantic_status", "zotero_topic_search",
    "zotero_search_literature", "zotero_get_item", "zotero_get_item_context", "zotero_get_pdf_text",
    "zotero_get_notes", "zotero_search_notes", "zotero_get_annotations", "zotero_list_collections",
    "zotero_get_collection_items", "zotero_list_tags", "zotero_get_selected_items",
    "zotero_get_current_reader_context", "zotero_get_workspace_snapshot", "zotero_lookup_journal_ranking",
    "zotero_cite_expand", "zotero_export_bibtex", "zotero_get_mcp_usage_guide",
    # import / organize (set to "needs approval" in the claude.ai connector)
    "zotero_import_papers", "zotero_create_collection", "zotero_add_items_to_collection",
    "zotero_add_tag", "zotero_write_note",
]
WRITE_TOOLS = {
    "zotero_import_papers", "zotero_create_collection", "zotero_add_items_to_collection", "zotero_add_tag",
    "zotero_write_note", "zotero_batch_write_notes", "zotero_write_collection_note", "zotero_batch_create_collections",
    "zotero_remove_items_from_collection", "zotero_remove_tags", "zotero_delete_tags_from_library",
    "zotero_organize_pdfs", "zotero_rename_pdf_attachments", "zotero_build_corpus", "zotero_build_knowledge_base",
    "zotero_auto_review", "zotero_generate_review", "zotero_generate_mindmap", "zotero_translate_fulltext",
    "zotero_run_ai_task", "zotero_compare_papers", "zotero_tracker_create_domain", "zotero_tracker_update_domain",
    "zotero_tracker_update_all_domains",
}
RISKY_TOOLS = {"zotero_delete_tags_from_library", "zotero_organize_pdfs", "zotero_rename_pdf_attachments",
               "zotero_remove_tags", "zotero_tracker_update_all_domains"}

SCHEMES = ("bearer", "x-api-key", "query")


def _transport(url: str, token: str, scheme: str):
    from fastmcp.client.transports import StreamableHttpTransport
    if scheme == "query":
        sep = "&" if "?" in url else "?"
        return StreamableHttpTransport(f"{url}{sep}token={token}")
    headers = {"Authorization": f"Bearer {token}"} if scheme == "bearer" else {"X-API-Key": token}
    return StreamableHttpTransport(url, headers=headers)


async def _list(url, token, scheme, timeout):
    from fastmcp import Client
    async with Client(_transport(url, token, scheme), timeout=timeout) as c:
        return sorted(t.name for t in await c.list_tools())


def probe(url: str, token: str, timeout: float = 15.0) -> dict:
    """Find the working auth scheme and the backend's tool list."""
    last = ""
    for scheme in SCHEMES:
        try:
            tools = asyncio.run(asyncio.wait_for(_list(url, token, scheme, timeout), timeout + 5))
            return {"ok": True, "scheme": scheme, "tools": tools}
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
    return {"ok": False, "error": last[:300]}


def mount_from_env(mcp) -> bool:
    """Called in the server child process. Mounts the AI4Paper proxy if configured via env."""
    token = os.environ.get("ZMC_AI4PAPER_TOKEN", "").strip()
    if not token:
        return False
    url = os.environ.get("ZMC_AI4PAPER_URL", DEFAULT_URL)
    scheme = os.environ.get("ZMC_AI4PAPER_SCHEME", "bearer")
    allowed = {n for n in os.environ.get("ZMC_AI4PAPER_TOOLS", "").split(",") if n}
    from fastmcp import Client
    from fastmcp.server import create_proxy
    from fastmcp.server.transforms.visibility import Visibility

    proxy = create_proxy(Client(_transport(url, token, scheme), timeout=120), name="AI4Paper")
    proxy.add_transform(Visibility(False, match_all=True))      # hide everything…
    if allowed:
        proxy.add_transform(Visibility(True, names=allowed))     # …then allow-list
    mcp.mount(proxy, namespace=NAMESPACE)
    return True
