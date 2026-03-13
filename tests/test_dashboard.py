"""Dashboard API/security tests."""
import os
import json
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import HTTPServer

from modules.config import CFG, SHARED, SHARED_LOCK
from modules.dashboard import DashHandler, _DIST_DIR


class DashboardServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), DashHandler)
        cls.port = cls.server.server_port
        CFG["dashboard_host"] = "127.0.0.1"
        CFG["dashboard_port"] = cls.port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _url(self, path):
        return f"http://127.0.0.1:{self.port}{path}"

    def test_state_contains_dry_run(self):
        req = Request(self._url("/api/state"), method="GET")
        with urlopen(req, timeout=2) as res:
            data = json.loads(res.read().decode())
        self.assertIn("dry_run", data)

    def test_toggle_rejects_non_local_origin(self):
        with SHARED_LOCK:
            SHARED["enabled"] = True
        req = Request(self._url("/api/toggle"), method="POST")
        req.add_header("Origin", "https://evil.example")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=2)
        self.assertEqual(ctx.exception.code, 403)
        with SHARED_LOCK:
            self.assertTrue(SHARED["enabled"])

    def test_toggle_allows_local_origin(self):
        with SHARED_LOCK:
            SHARED["enabled"] = True
        req = Request(self._url("/api/toggle"), method="POST")
        req.add_header("Origin", f"http://127.0.0.1:{self.port}")
        with urlopen(req, timeout=2) as res:
            body = json.loads(res.read().decode())
        self.assertIn("enabled", body)
        with SHARED_LOCK:
            self.assertFalse(SHARED["enabled"])

    @unittest.skipUnless(os.path.isdir(_DIST_DIR), "dist directory required")
    def test_static_path_traversal_forbidden(self):
        req = Request(self._url("/../../kalshi-config.json"), method="GET")
        with self.assertRaises(HTTPError) as ctx:
            urlopen(req, timeout=2)
        self.assertEqual(ctx.exception.code, 403)


if __name__ == "__main__":
    unittest.main()
