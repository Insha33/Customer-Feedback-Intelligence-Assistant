import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from backend import reviewlens_server
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

    def test_health_reports_request_scoped_sqlite_connections(self):
        status, _headers, body = self.request("/api/health")

        self.assertEqual(status, 200)
        self.assertEqual(
            json.loads(body)["sqlite_connection_scope"],
            "request",
        )

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

    def test_structured_analytics_supports_concurrent_request_threads(self):
        def reset_sql_cache():
            with reviewlens_server.SQL_CACHE_LOCK:
                reviewlens_server.SQL_CACHE.update(
                    {"mtime": None, "rows": [], "categories": []}
                )

        csv_content = "\n".join(
            [
                "review_id,source,user_rating,review_text,category,review_date,sentiment,quality_score",
                "1,app_store,1,Locked out,Account Access,2026-07-01,negative,0.9",
                "2,play_store,5,Works well,Usability,2026-07-02,positive,0.8",
            ]
        )

        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "reviews.csv"
            csv_path.write_text(csv_content, encoding="utf-8")

            with patch.object(reviewlens_server, "REVIEW_CSV", csv_path):
                reset_sql_cache()
                self.addCleanup(reset_sql_cache)

                with ThreadPoolExecutor(max_workers=8) as executor:
                    results = list(
                        executor.map(
                            reviewlens_server.structured_analytics_context,
                            ["What is the sentiment split?"] * 16,
                        )
                    )

        self.assertTrue(
            all("- Matching reviews: 2 of 2 (100%)" in result for result in results)
        )


if __name__ == "__main__":
    unittest.main()
