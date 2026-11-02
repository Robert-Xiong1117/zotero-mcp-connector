"""Full dependency tests: run in CI; no real account or socket required."""
import importlib.util
import base64
import hashlib
import tempfile
import unittest
from urllib.parse import urlencode, urlsplit, parse_qs

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

    async def test_oauth_pkce_login_token_and_restart(self):
        from cloud.server import build_server
        app = self.server.http_app()
        verifier = "v" * 64
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                          base_url=self.settings.public_url) as client:
                registered = await client.post("/register", json={
                    "client_name": "Cloud integration test", "redirect_uris": ["https://client.example/callback"],
                    "token_endpoint_auth_method": "none", "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"], "scope": "zotero.read"})
                self.assertEqual(registered.status_code, 201, registered.text)
                client_id = registered.json()["client_id"]
                query = urlencode({"client_id": client_id, "redirect_uri": "https://client.example/callback",
                    "response_type": "code", "code_challenge": challenge, "code_challenge_method": "S256",
                    "scope": "zotero.read", "state": "test-state"})
                denied = await client.get("/authorize?" + query)
                self.assertIn("/authorize/login", denied.headers["location"])
                bad_login = await client.post("/authorize/login", data={"password": "incorrect", "next": query})
                self.assertNotIn("set-cookie", bad_login.headers)
                login = await client.post("/authorize/login", data={"password": self.settings.admin_password, "next": query})
                self.assertEqual(login.status_code, 303)
                authorized = await client.get(login.headers["location"])
                self.assertIn(authorized.status_code, (302, 303, 307))
                args = parse_qs(urlsplit(authorized.headers["location"]).query)
                self.assertEqual(args["state"], ["test-state"])
                token = await client.post("/token", data={"grant_type": "authorization_code",
                    "client_id": client_id, "code": args["code"][0], "code_verifier": verifier,
                    "redirect_uri": "https://client.example/callback"})
                self.assertEqual(token.status_code, 200, token.text)
                access = token.json()["access_token"]
                # Persisted tokens survive a new server instance; no desktop needed.
                restarted = build_server(self.settings, self.api)
                self.assertIsNotNone(await restarted.auth.load_access_token(access))
                replay = await client.post("/token", data={"grant_type": "authorization_code",
                    "client_id": client_id, "code": args["code"][0], "code_verifier": verifier,
                    "redirect_uri": "https://client.example/callback"})
                self.assertEqual(replay.status_code, 400)


if __name__ == "__main__":
    unittest.main()

