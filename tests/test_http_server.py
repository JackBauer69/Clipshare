from http.cookiejar import CookieJar
from http.client import HTTPConnection
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import io
import json
import os
import socket
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from clipshare import clipboard_share
from clipshare.instance import SingleInstanceLock


class ClipShareHTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = clipboard_share.ShareServer(host="127.0.0.1", port=0).start()
        self.base_url = f"http://127.0.0.1:{self.server.port}"
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def tearDown(self):
        self.server.stop()

    def request(self, path, data=None, headers=None, method=None):
        request = Request(self.base_url + path, data=data, headers=headers or {}, method=method)
        try:
            with self.opener.open(request, timeout=10) as response:
                return response.status, response.read(), response.headers
        except HTTPError as error:
            with error:
                return error.code, error.read(), error.headers

    def post_json(self, path, payload):
        return self.request(
            path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

    def join(self):
        status, _body, headers = self.post_json("/auth", {"code": self.server.state.pairing_code.lower()})
        self.assertEqual(status, 200)
        self.assertIn("HttpOnly", headers.get("Set-Cookie", ""))
        self.assertIn("SameSite=Strict", headers.get("Set-Cookie", ""))

    def test_pairing_is_required_before_content_routes(self):
        status, page, _headers = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Enter the temporary session code", page)
        status, _body, _headers = self.request("/messages")
        self.assertEqual(status, 401)
        status, _body, _headers = self.post_json("/messages", {"text": "private"})
        self.assertEqual(status, 401)

        self.join()
        status, page, _headers = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Share selected files", page)
        status, messages, _headers = self.request("/messages")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(messages), [])

    def test_pairing_attempts_are_rate_limited(self):
        for _ in range(clipboard_share.AUTH_ATTEMPT_LIMIT):
            status, _body, _headers = self.post_json("/auth", {"code": "AAAAAAAAAAAA"})
            self.assertEqual(status, 401)
        status, _body, _headers = self.post_json("/auth", {"code": self.server.state.pairing_code})
        self.assertEqual(status, 429)

    def test_text_submission_and_message_limit(self):
        self.join()
        for number in range(clipboard_share.MAX_MESSAGES + 1):
            status, _body, _headers = self.post_json("/messages", {"text": f"message-{number}"})
            self.assertEqual(status, 201)
        status, body, _headers = self.request("/messages")
        messages = json.loads(body)
        self.assertEqual(status, 200)
        self.assertEqual(len(messages), clipboard_share.MAX_MESSAGES)
        self.assertEqual(messages[0]["text"], "message-1")
        self.assertEqual(messages[-1]["text"], f"message-{clipboard_share.MAX_MESSAGES}")

        status, _body, _headers = self.post_json("/messages", {"text": ""})
        self.assertEqual(status, 400)
        oversized = "x" * clipboard_share.MAX_MESSAGE_BYTES
        # The server rejects from Content-Length without consuming an oversized
        # body. Send only headers so the client does not race the response by
        # continuing to transmit data on a connection the server will close.
        token = next(iter(self.server.state.sessions))
        connection = HTTPConnection("127.0.0.1", self.server.port, timeout=5)
        try:
            connection.putrequest("POST", "/messages")
            connection.putheader("Cookie", f"{clipboard_share.COOKIE_NAME}={token}")
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", str(len(json.dumps({"text": oversized}).encode("utf-8"))))
            connection.putheader("Connection", "close")
            connection.endheaders()
            response = connection.getresponse()
            self.assertEqual(response.status, 413)
            self.assertEqual(response.getheader("Connection"), "close")
            self.assertIn(b"200 KB max", response.read())
        finally:
            connection.close()

    def test_file_upload_download_and_zip_preserve_folder_paths(self):
        self.join()
        content = b"ClipShare test content\x00"
        status, body, _headers = self.post_json(
            "/upload/start",
            {"files": [{"name": "project/docs/readme.txt", "size": len(content)}]},
        )
        self.assertEqual(status, 201)
        batch_id = json.loads(body)["id"]

        status, _body, _headers = self.request(
            f"/upload/{batch_id}/0",
            data=content,
            headers={"Content-Type": "application/octet-stream", "X-Chunk-Offset": "0"},
            method="POST",
        )
        self.assertEqual(status, 200)
        status, _body, _headers = self.request(f"/upload/{batch_id}/finish", data=b"", method="POST")
        self.assertEqual(status, 201)

        status, body, _headers = self.request("/files")
        self.assertEqual(status, 200)
        batch = json.loads(body)[0]
        item = batch["files"][0]
        self.assertEqual(item["path"], "project/docs/readme.txt")

        status, downloaded, headers = self.request(f"/file/{batch_id}/{quote(item['id'])}")
        self.assertEqual(status, 200)
        self.assertEqual(downloaded, content)
        self.assertEqual(headers.get_content_type(), "application/octet-stream")

        status, archive_data, headers = self.request(f"/files/{batch_id}.zip")
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), "application/zip")
        with zipfile.ZipFile(io.BytesIO(archive_data)) as archive:
            self.assertEqual(archive.namelist(), ["project/docs/readme.txt"])
            self.assertEqual(archive.read("project/docs/readme.txt"), content)

    def test_filename_and_size_validation(self):
        self.join()
        bad_names = (
            "../outside.txt", "/absolute.txt", "C:\\private\\file.txt", "folder/../../x",
            "folder/file:stream", "folder/CON.txt", "folder/trailing.",
        )
        for name in bad_names:
            with self.subTest(name=name):
                status, _body, _headers = self.post_json(
                    "/upload/start", {"files": [{"name": name, "size": 1}]}
                )
                self.assertEqual(status, 400)

        status, _body, _headers = self.post_json(
            "/upload/start",
            {"files": [{"name": "same.txt", "size": 0}, {"name": "same.txt", "size": 0}]},
        )
        self.assertEqual(status, 400)

        for item in (
            {"name": "file.bin", "size": -1},
            {"name": "file.bin", "size": True},
            {"name": "file.bin", "size": clipboard_share.MAX_UPLOAD_BYTES + 1},
        ):
            status, _body, _headers = self.post_json("/upload/start", {"files": [item]})
            self.assertEqual(status, 400)

    def test_storage_and_batch_limits(self):
        self.join()
        with patch.object(clipboard_share, "MAX_STORED_BYTES", 2):
            status, _body, _headers = self.post_json(
                "/upload/start", {"files": [{"name": "large.bin", "size": 3}]}
            )
        self.assertEqual(status, 413)

        with patch.object(clipboard_share, "MAX_UPLOAD_BATCHES", 1):
            status, _body, _headers = self.post_json(
                "/upload/start", {"files": [{"name": "first.bin", "size": 0}]}
            )
            self.assertEqual(status, 201)
            status, _body, _headers = self.post_json(
                "/upload/start", {"files": [{"name": "second.bin", "size": 0}]}
            )
            self.assertEqual(status, 413)

    def test_file_count_limit_includes_empty_files_and_cleans_up(self):
        self.join()
        storage_root = Path(self.server.state.storage_root)
        files = [{"name": f"empty-{index}.txt", "size": 0} for index in range(clipboard_share.MAX_FILES_PER_BATCH)]
        status, body, _headers = self.post_json("/upload/start", {"files": files})
        self.assertEqual(status, 201)
        batch_id = json.loads(body)["id"]
        batch_directory = storage_root / batch_id
        self.assertEqual(len(list(batch_directory.iterdir())), clipboard_share.MAX_FILES_PER_BATCH)

        excessive_files = files + [{"name": "one-too-many.txt", "size": 0}]
        status, body, _headers = self.post_json("/upload/start", {"files": excessive_files})
        self.assertEqual(status, 413)
        self.assertIn(b"at most 1,000 files", body)
        self.assertEqual(list(storage_root.iterdir()), [batch_directory])
        self.assertEqual(len(self.server.state.pending_uploads), 1)

        self.server.stop()
        self.assertFalse(storage_root.exists())

    def test_empty_file_and_invalid_chunk_offsets(self):
        self.join()
        status, body, _headers = self.post_json(
            "/upload/start", {"files": [{"name": "empty.txt", "size": 0}]}
        )
        self.assertEqual(status, 201)
        batch_id = json.loads(body)["id"]
        status, _body, _headers = self.request(f"/upload/{batch_id}/finish", data=b"", method="POST")
        self.assertEqual(status, 201)
        status, batches, _headers = self.request("/files")
        item = json.loads(batches)[0]["files"][0]
        status, downloaded, _headers = self.request(f"/file/{batch_id}/{item['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(downloaded, b"")

        status, body, _headers = self.post_json(
            "/upload/start", {"files": [{"name": "data.bin", "size": 3}]}
        )
        batch_id = json.loads(body)["id"]
        status, _body, _headers = self.request(
            f"/upload/{batch_id}/0",
            data=b"abc",
            headers={"Content-Type": "application/octet-stream", "X-Chunk-Offset": "1"},
            method="POST",
        )
        self.assertEqual(status, 400)
        status, _body, _headers = self.request(f"/upload/{batch_id}/finish", data=b"", method="POST")
        self.assertEqual(status, 400)

    def test_cleanup_removes_temporary_upload_data(self):
        self.join()
        status, _body, _headers = self.post_json(
            "/upload/start", {"files": [{"name": "unfinished.bin", "size": 10}]}
        )
        self.assertEqual(status, 201)
        storage_root = Path(self.server.state.storage_root)
        self.assertTrue(storage_root.is_dir())
        self.server.stop()
        self.assertFalse(storage_root.exists())

    def test_port_conflict_uses_an_available_port(self):
        occupied = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        occupied.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        blocked_port = occupied.getsockname()[1]
        alternate = None
        try:
            alternate = clipboard_share.ShareServer(host="127.0.0.1", port=blocked_port).start()
            self.assertTrue(alternate.port_fallback)
            self.assertNotEqual(alternate.port, blocked_port)
        finally:
            if alternate:
                alternate.stop()
            occupied.close()

    @unittest.skipUnless(os.name == "nt", "Windows-specific exclusive bind regression")
    def test_windows_servers_cannot_share_a_listening_port(self):
        first = clipboard_share.ShareServer(host="127.0.0.1", port=0).start()
        second = None
        try:
            second = clipboard_share.ShareServer(host="127.0.0.1", port=first.port).start()
            self.assertTrue(second.port_fallback)
            self.assertNotEqual(second.port, first.port)
        finally:
            if second is not None:
                second.stop()
            first.stop()

    def test_stop_and_restart_creates_a_fresh_temporary_session(self):
        first = clipboard_share.ShareServer(host="127.0.0.1", port=0).start()
        first_storage = Path(first.state.storage_root)
        first_code = first.state.pairing_code
        first.stop()
        self.assertFalse(first_storage.exists())

        second = clipboard_share.ShareServer(host="127.0.0.1", port=0).start()
        try:
            self.assertNotEqual(second.state.pairing_code, first_code)
            with urlopen(f"http://127.0.0.1:{second.port}/", timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(b"Join ClipShare", response.read())
        finally:
            second.stop()

    def test_server_stop_failure_can_be_retried(self):
        session = clipboard_share.ShareServer(host="127.0.0.1", port=0).start()
        original_shutdown = session.httpd.shutdown
        try:
            with patch.object(
                session.httpd,
                "shutdown",
                side_effect=[RuntimeError("simulated listener shutdown failure"), original_shutdown],
            ):
                with self.assertRaisesRegex(RuntimeError, "simulated listener shutdown failure"):
                    session.stop()
            self.assertFalse(session._stopped)
            self.assertTrue(session.thread.is_alive())
            session.stop()
            self.assertTrue(session._stopped)
            self.assertFalse(session.thread.is_alive())
        finally:
            if not session._stopped:
                session.stop()

    def test_slow_chunk_does_not_block_an_unrelated_upload_batch(self):
        self.join()
        batch_ids = []
        for name in ("slow.bin", "other.bin"):
            status, body, _headers = self.post_json(
                "/upload/start", {"files": [{"name": name, "size": 1}]}
            )
            self.assertEqual(status, 201)
            batch_ids.append(json.loads(body)["id"])

        token = next(iter(self.server.state.sessions))
        with socket.create_connection(("127.0.0.1", self.server.port), timeout=5) as stalled_client:
            stalled_client.settimeout(5)
            stalled_client.sendall(
                (
                    f"POST /upload/{batch_ids[0]}/0 HTTP/1.1\r\n"
                    f"Host: 127.0.0.1:{self.server.port}\r\n"
                    f"Cookie: {clipboard_share.COOKIE_NAME}={token}\r\n"
                    "Content-Type: application/octet-stream\r\n"
                    "X-Chunk-Offset: 0\r\n"
                    "Content-Length: 1\r\n"
                    "Connection: close\r\n\r\n"
                ).encode("ascii")
            )

            started = time.monotonic()
            with ThreadPoolExecutor(max_workers=1) as executor:
                other_chunk = executor.submit(
                    self.request,
                    f"/upload/{batch_ids[1]}/0",
                    b"B",
                    {"Content-Type": "application/octet-stream", "X-Chunk-Offset": "0"},
                    "POST",
                )
                try:
                    status, _body, _headers = other_chunk.result(timeout=5)
                except FutureTimeoutError:
                    stalled_client.sendall(b"A")
                    while stalled_client.recv(4096):
                        pass
                    self.fail("A slow upload chunk blocked an unrelated batch.")
            self.assertEqual(status, 200)
            self.assertLess(time.monotonic() - started, 5)

            stalled_client.sendall(b"A")
            first_response = bytearray()
            while True:
                chunk = stalled_client.recv(4096)
                if not chunk:
                    break
                first_response.extend(chunk)
            self.assertIn(b" 200 ", first_response.split(b"\r\n", 1)[0])

        for batch_id in batch_ids:
            status, _body, _headers = self.request(f"/upload/{batch_id}/finish", data=b"", method="POST")
            self.assertEqual(status, 201)


class SingleInstanceTests(unittest.TestCase):
    def test_lock_prevents_second_instance_and_exposes_running_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clipshare.lock"
            first = SingleInstanceLock(path)
            second = SingleInstanceLock(path)
            try:
                self.assertTrue(first.acquire())
                self.assertNotEqual(first.state_path, first.path)
                first.write_state({"running": True, "port": 3570})
                self.assertTrue(first.state_path.is_file())
                self.assertFalse(second.acquire())
                self.assertEqual(second.read_state(), {"running": True, "port": 3570})
                first.release()
                self.assertTrue(second.acquire())
            finally:
                second.release()
                first.release()


if __name__ == "__main__":
    unittest.main()
