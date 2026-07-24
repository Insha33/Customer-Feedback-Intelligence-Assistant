import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

from backend.reviewlens_server import ReviewLensHandler


class ReviewLensServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ReviewLensHandler)
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def request(self, path):
        connection = HTTPConnection(
            "127.0.0.1",
            self.server.server_port,
            timeout=5,
        )
        connection.request("GET", path)
        response = connection.getresponse()
        body = response.read()
        headers = {
            name.lower(): value for name, value in response.getheaders()
        }
        connection.close()
        return response.status, headers, body

    def test_root_serves_dashboard_with_root_asset_paths(self):
        status, _headers, body = self.request("/")

        self.assertEqual(status, 200)
        self.assertIn(b'href="/styles.css?', body)
        self.assertIn(b'src="/app.js?', body)

    def test_root_stylesheet_is_served(self):
        status, headers, body = self.request("/styles.css")

        self.assertEqual(status, 200)
        self.assertTrue(headers["content-type"].startswith("text/css"))
        self.assertIn(b":root", body)

    def test_backlog_serves_page_with_canonical_links(self):
        status, _headers, body = self.request("/backlog")

        self.assertEqual(status, 200)
        self.assertIn(b'href="/backlog"', body)
        self.assertIn(b'src="/backlog.js?', body)

    def test_old_frontend_routes_redirect_to_canonical_paths(self):
        status, headers, _body = self.request("/frontend/")
        self.assertEqual(status, 307)
        self.assertEqual(headers["location"], "/")

        status, headers, _body = self.request("/frontend/backlog.html")
        self.assertEqual(status, 307)
        self.assertEqual(headers["location"], "/backlog")


if __name__ == "__main__":
    unittest.main()
