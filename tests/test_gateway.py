import sys
import threading
from http.client import HTTPConnection
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import gateway as gw


class GatewayTests(unittest.TestCase):
    def test_slots_are_independent(self):
        paths = set()
        for n in range(1, 11):
            route = f"/s/{n}/app/com.example.app"
            self.assertEqual(gw.PAGE.fullmatch(route).groups(), (str(n), "app/com.example.app", "com.example.app"))
            self.assertTrue(gw.PAGE.fullmatch(f"/s/{n}/home"))
            url = urlsplit(gw.viewer(n))
            self.assertEqual(url.path, f"/s/{n}/view/vnc.html")
            self.assertEqual(parse_qs(url.query)["path"], [f"s/{n}/view/websockify"])
            paths.add(url.path)
        self.assertEqual(len(paths), 10)

    def test_path_validation(self):
        for path in ["/s/11/home", "/s/0/home", "/s/01/home", "/s/1/app/com.bad%3Bwhoami",
                     "/s/1/app/com.foo;id", "/s/1/app/com.foo/extra", "/s/1/app/-pkg", "/s/1/app/com.a?x=y"]:
            self.assertIsNone(gw.PAGE.fullmatch(path))

    def test_origin_port(self):
        self.assertEqual(gw.origin_value("https://sam.home.arpa:443"), "https://sam.home.arpa")
        for value in ("https://SAM.home", "https://sam:0", "https://sam:99999", "http://sam", "https://sam/abc"):
            with self.assertRaises(ValueError):
                gw.origin_value(value)

    def test_tokens_bound_to_slot_and_action(self):
        self.assertNotEqual(gw.csrf_token("/s/1/home", 10), gw.csrf_token("/s/10/home", 10))
        self.assertNotEqual(gw.csrf_token("/s/1/home", 10), gw.csrf_token("/s/1/app/x.y", 10))

    @patch("gateway.adb", side_effect=[(True, "1"), (True, "OtherAvd\nOK")])
    def test_wrong_avd_rejected(self, adb):
        self.assertEqual(gw.open_guest(1, "org.example", "launch")[0], 409)
        self.assertEqual(adb.call_count, 2)

    @patch("gateway.socket.create_connection")
    @patch("gateway.adb")
    def test_launcher_component_only_from_requested_package(self, adb, socket):
        for bad in ("com.other/.Activity", "com.example/.Activity;id", "No activity found"):
            adb.side_effect = [(True, "1"), (True, "SamDevice10\nOK"), (True, bad)]
            code, response = gw.open_guest(10, "com.example", "launch")
            self.assertEqual(code, 409)
            self.assertTrue(response["alternatives"])

    @patch("gateway.socket.create_connection")
    @patch("gateway.adb", side_effect=[(True, "1"), (True, "SamDevice10\nOK"), (True, "com.example/.A$B"), (True, "Starting")])
    def test_open_slot_ten(self, adb, socket):
        code, result = gw.open_guest(10, "com.example", "launch")
        self.assertEqual(code, 200)
        self.assertEqual(result["viewer"], gw.viewer(10))
        self.assertEqual(adb.call_args.args, (10, "shell", "am", "start", "-n", "'com.example/.A$B'"))

    @patch("gateway.ensure_running")
    @patch("gateway.adb", return_value=(False, "offline"))
    def test_start_only_requested_guest(self, adb, start):
        self.assertEqual(gw.open_guest(3, None, "launch")[0], 202)
        start.assert_called_once_with(3)

    @patch("gateway.socket.create_connection")
    @patch("gateway.adb")
    def test_store_and_android_home(self, adb, sock):
        for action in ["store", "home"]:
            adb.side_effect = [(True, "1"), (True, "SamDevice01\nOK"), (True, "Starting")]
            self.assertEqual(gw.open_guest(1, "com.test", action)[0], 200)
            args = adb.call_args.args
            if action == "store":
                self.assertIn("market://details?id=com.test", args)
                self.assertIn("com.android.vending", args)
            else:
                self.assertIn("android.intent.category.HOME", args)

class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.server = gw.ThreadingHTTPServer(("127.0.0.1", 0), gw.Controller)
        self.server.public_origin = "https://sam.home.arpa:8443"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, headers, body=None):
        connection = HTTPConnection(*self.server.server_address, timeout=2)
        try:
            connection.request(method, "/s/10/home", headers=headers, body=body)
            response = connection.getresponse()
            return response.status, response.read().decode()
        finally:
            connection.close()

    @patch.object(gw.Controller, "log_request")
    def test_navigation_requires_user_gesture_for_untrusted_referrers(self, unused_log):
        for origin, destination, expected in [("none","document",True), ("same-origin","document",True),
                                             ("cross-site","document",False), ("same-origin","iframe",False)]:
            code, body = self.request("GET", {"Sec-Fetch-Site": origin, "Sec-Fetch-Dest": destination,
                                              "Sec-Fetch-Mode": "navigate"})
            self.assertEqual(code, 200)
            self.assertEqual('launch("launch");</script>' in body, expected)

    @patch.object(gw.Controller, "log_request")
    @patch.object(gw, "open_guest", return_value=(200, {"viewer": "/stub"}))
    def test_csrf_origin_and_token(self, launch, unused_log):
        token = gw.csrf_token("/s/10/home", int(gw.time.time() // 1800))
        for origin, candidate, expected in [(self.server.public_origin, "", 403),
                                            ("https://other.local", token, 403),
                                            (self.server.public_origin, token, 200)]:
            code, body = self.request("POST", {"Origin": origin, "X-Sam-CSRF": candidate,
                                               "Content-Type": "application/json"}, '{"action":"home"}')
            self.assertEqual(code, expected)
        launch.assert_called_once_with(10, None, "home")


if __name__ == "__main__":
    unittest.main()
