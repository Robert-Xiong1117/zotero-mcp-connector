"""Full dependency tests: run in CI; no real account or socket required."""
import importlib.util
import tempfile
import unittest

import httpx

from cloud.client import CloudClient
from cloud.config import Settings

HAS_MCP = importlib.util.find_spec("fastmcp") is not None


@unittest.skipUnless(HAS_MCP, "Install requirements-cloud.txt for MCP integration tests")
class MCPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from cloud.server import build_server
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.settings = Settings(library_id="123456", api_key="test-private-key",
            public_url="https://mcp.example.com", admin_password="test-password-with-at-least-24-chars",
            data_dir=self.tmp.name)
        self.api = CloudClient(self.settings, transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=[], headers={"Total-Results": "0"})))
        self.addCleanup(self.api.close)
        self.server = build_server(self.settings, self.api)

    async def test_tools_and_real_mcp_call(self):
        from fastmcp import Client
        async with Client(self.server) as client:
            tools = await client.list_tools()
            names = {t.name for t in tools}
            self.assertEqual(len(names), 14)
            self.assertIn("read_pdf_pages", names)
            self.assertNotIn("create_note", names)
            result = await client.call_tool("search_items", {"query": "persona"})
            self.assertFalse(result.is_error)

    async def test_http_auth_and_discovery(self):
        app = self.server.http_app()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                          base_url=self.settings.public_url) as client:
                self.assertEqual((await client.get("/healthz")).status_code, 200)
                self.assertEqual((await client.post("/mcp", json={})).status_code, 401)
                discovery = await client.get("/.well-known/oauth-authorization-server")
                self.assertEqual(discovery.status_code, 200)
                self.assertEqual((await client.post("/authorize", data={})).status_code, 405)
                denied = await client.get("/authorize?client_id=unknown")
                self.assertIn(denied.status_code, (302, 303, 307))
                self.assertIn("/authorize/login", denied.headers["location"])

    async def test_cimd_rejects_untrusted_url_without_fetch(self):
        self.assertIsNone(await self.server.auth.get_client("http://127.0.0.1/internal"))
        self.assertIsNone(await self.server.auth.get_client("https://169.254.169.254/latest"))


if __name__ == "__main__":
    unittest.main()
