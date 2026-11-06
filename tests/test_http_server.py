import json
from http.server import ThreadingHTTPServer
from threading import Thread
import unittest
from urllib.request import Request, urlopen

from clipshare import clipboard_share


class ClipboardShareHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), clipboard_share.Handler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_home_page_and_empty_lists(self):
        with urlopen(self.base_url + "/") as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"Clipboard Share", response.read())
        with urlopen(self.base_url + "/messages") as response:
            self.assertEqual(json.load(response), [])
        with urlopen(self.base_url + "/files") as response:
            self.assertEqual(json.load(response), [])

    def test_posted_text_is_listed(self):
        request = Request(
            self.base_url + "/messages",
            data=json.dumps({"text": "clipboard test"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            self.assertEqual(response.status, 201)
        with urlopen(self.base_url + "/messages") as response:
            messages = json.load(response)
        self.assertEqual(messages[-1]["text"], "clipboard test")


if __name__ == "__main__":
    unittest.main()
