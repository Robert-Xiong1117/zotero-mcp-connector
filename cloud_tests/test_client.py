import io
import json
import unittest
from dataclasses import replace

import httpx
from pypdf import PdfWriter

from cloud.client import CloudClient, CloudError, MAX_PDF_BYTES
from cloud.config import Settings


def settings(**kwargs):
    values = dict(library_id="123456", api_key="private-api-key", public_url="https://mcp.example.com",
                  admin_password="random-admin-password-1234567890")
    return Settings(**(values | kwargs))


def pdf():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_blank_page(width=100, height=100)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def attachment(version=1, link_mode="imported_file"):
    return {"key": "ABCD2345", "version": version, "data": {
        "key": "ABCD2345", "itemType": "attachment", "linkMode": link_mode,
        "contentType": "application/pdf", "md5": "example-hash"}}


class ClientTests(unittest.TestCase):
    def client(self, handler):
        client = CloudClient(settings(), transport=httpx.MockTransport(handler))
        self.addCleanup(client.close)
        return client

    def test_pagination_does_not_drop_items_after_first_page(self):
        def handle(req):
            start = int(req.url.params["start"])
            return httpx.Response(200, json=[{"n": n} for n in range(start, min(start + 100, 205))],
                                  headers={"Total-Results": "205", "Last-Modified-Version": "12"})
        client = self.client(handle)
        found, start = [], 0
        while start is not None:
            result = client.page("/items", start=start, limit=100)
            found += result["data"]
            start = result["next_start"]
        self.assertEqual(len(found), 205)
        self.assertEqual(result["library_version"], "12")

    def test_cloud_url_and_headers(self):
        def handle(req):
            self.assertEqual(req.url.host, "api.zotero.org")
            self.assertEqual(req.url.path, "/users/123456/items/ABCD2345")
            self.assertEqual(req.headers["Zotero-API-Key"], "private-api-key")
            self.assertEqual(req.headers["Zotero-API-Version"], "3")
            return httpx.Response(200, json=attachment())
        self.client(handle).item("ABCD2345")

    def test_group_url(self):
        client = CloudClient(settings(library_type="group"), transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=attachment())))
        self.addCleanup(client.close)
        self.assertEqual(client.prefix, "/groups/123456")
        self.assertIn("groups/123456", client.item("ABCD2345")["source"]["desktop"])

    def test_invalid_keys_and_limits_rejected_before_network(self):
        client = self.client(lambda r: self.fail("Unexpected network call"))
        for value in ("../secret", "a?key=xxx", "ABC", "ABCD2345/file"):
            with self.assertRaises(ValueError):
                client.item(value)
        with self.assertRaises(ValueError):
            client.page("/items", limit=101)
        with self.assertRaises(ValueError):
            client.pdf_pages("ABCD2345", page_count=11)

    def test_errors_do_not_echo_upstream_secrets(self):
        client = self.client(lambda r: httpx.Response(403, text="private-api-key secret"))
        with self.assertRaises(CloudError) as caught:
            client.item("ABCD2345")
        self.assertNotIn("private-api-key", str(caught.exception))

    def test_429_stops_subsequent_requests(self):
        calls = []
        def handle(req):
            calls.append(req)
            return httpx.Response(429, headers={"Retry-After": "60"})
        client = self.client(handle)
        for _ in range(2):
            with self.assertRaises(CloudError):
                client.item("ABCD2345")
        self.assertEqual(len(calls), 1)

    def test_success_backoff_is_respected(self):
        client = self.client(lambda r: httpx.Response(200, json=attachment(), headers={"Backoff": "60"}))
        client.item("ABCD2345")
        with self.assertRaises(CloudError):
            client.item("ABCD2345")

    def test_fulltext_pagination_preserves_completeness_metadata(self):
        client = self.client(lambda r: httpx.Response(200, json={"content": "abcdefghij",
                                                    "indexedPages": 1, "totalPages": 5}))
        result = client.fulltext("ABCD2345", offset=2, max_chars=3)
        self.assertEqual(result["content"], "cde")
        self.assertEqual(result["next_offset"], 5)
        self.assertEqual(result["indexedPages"], 1)
        self.assertEqual(result["totalPages"], 5)

    def test_annotations_have_separate_physical_and_printed_pages(self):
        client = self.client(lambda r: None)
        result = client.with_links({"key": "ANNO2345", "data": {"itemType": "annotation",
            "parentItem": "ABCD2345", "annotationPageLabel": "iv",
            "annotationPosition": json.dumps({"pageIndex": 3})}})
        self.assertEqual(result["source"]["pdf_page"], 4)
        self.assertEqual(result["source"]["page_label"], "iv")
        self.assertIn("annotation=ANNO2345", result["source"]["annotation"])

    def test_collection_links_are_not_item_links(self):
        client = self.client(lambda r: None)
        self.assertIn("/collections/", client.with_links({"key": "ABCD2345", "data": {"name": "A"}})["source"]["api"])

    def test_pdf_redirect_strips_secret_and_cache_invalidates_on_version(self):
        calls = []
        version = [1]
        blob = pdf()
        def handle(req):
            calls.append(req)
            if req.url.path.endswith("/file"):
                return httpx.Response(302, headers={"Location": "https://zotero.s3.us-east-1.amazonaws.com/file.pdf"})
            if req.url.host.endswith("amazonaws.com"):
                self.assertNotIn("Zotero-API-Key", req.headers)
                self.assertNotIn("Authorization", req.headers)
                return httpx.Response(200, content=blob)
            return httpx.Response(200, json=attachment(version[0]))
        client = self.client(handle)
        self.assertEqual(client.pdf_bytes("ABCD2345"), blob)
        client.pdf_bytes("ABCD2345")
        self.assertEqual(sum(r.url.path.endswith("/file") for r in calls), 1)
        version[0] = 2
        client.pdf_bytes("ABCD2345")
        self.assertEqual(sum(r.url.path.endswith("/file") for r in calls), 2)

    def test_pdf_blocked_redirects(self):
        for destination in ("http://127.0.0.1/secret", "https://evil.example/x", "file:///etc/passwd"):
            def handle(req):
                if req.url.path.endswith("/file"):
                    return httpx.Response(302, headers={"Location": destination})
                return httpx.Response(200, json=attachment())
            with self.assertRaises(CloudError):
                self.client(handle).pdf_bytes("ABCD2345")

    def test_linked_file_and_missing_cloud_file(self):
        with self.assertRaises(CloudError):
            self.client(lambda r: httpx.Response(200, json=attachment(link_mode="linked_file"))).pdf_bytes("ABCD2345")
        def handle(req):
            return httpx.Response(404) if req.url.path.endswith("/file") else httpx.Response(200, json=attachment())
        with self.assertRaises(CloudError):
            self.client(handle).pdf_bytes("ABCD2345")

    def test_large_and_non_pdf_files(self):
        for response in (httpx.Response(200, headers={"Content-Length": str(MAX_PDF_BYTES + 1)}),
                         httpx.Response(200, content=b"<html>not a pdf</html>")):
            def handle(req):
                return response if req.url.path.endswith("/file") else httpx.Response(200, json=attachment())
            with self.assertRaises(CloudError):
                self.client(handle).pdf_bytes("ABCD2345")

    def test_pdf_page_offsets_and_ocr_signal(self):
        client = self.client(lambda r: httpx.Response(200, content=pdf()) if r.url.path.endswith("/file")
                             else httpx.Response(200, json=attachment()))
        result = client.pdf_pages("ABCD2345", page_count=1)
        self.assertEqual(result["next_page"], 2)
        self.assertEqual(result["pages"][0]["pdf_page"], 1)
        self.assertTrue(result["pages"][0]["needs_ocr"])
        self.assertIsNone(client.pdf_pages("ABCD2345", start_page=2)["next_page"])

    def test_export_validates_keys(self):
        client = self.client(lambda r: httpx.Response(200, text="@article{example}"))
        self.assertEqual(client.export(["ABCD2345"]), "@article{example}")
        with self.assertRaises(ValueError):
            client.export([])


class ConfigTests(unittest.TestCase):
    def test_cloud_config_rejects_local_defaults_and_unsafe_origin(self):
        for kwargs in ({"library_id": "0"}, {"api_key": ""}, {"public_url": "http://localhost"},
                       {"public_url": "https://mcp.example.com/mcp"}, {"admin_password": "short"}):
            with self.assertRaises(ValueError):
                settings(**kwargs)

    def test_secrets_not_in_repr(self):
        self.assertNotIn("private-api-key", repr(settings()))
        self.assertNotIn("random-admin-password", repr(settings()))


if __name__ == "__main__":
    unittest.main()
