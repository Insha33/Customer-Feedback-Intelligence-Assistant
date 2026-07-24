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

    def test_root_redirects_to_canonical_frontend_path(self):
        status, headers, _body = self.request("/")

        self.assertEqual(status, 307)
        self.assertEqual(headers["location"], "/frontend/")

    def test_frontend_stylesheet_is_served(self):
        status, headers, body = self.request("/frontend/styles.css")

        self.assertEqual(status, 200)
        self.assertTrue(headers["content-type"].startswith("text/css"))
        self.assertIn(b":root", body)


if __name__ == "__main__":
    unittest.main()
