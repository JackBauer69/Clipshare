#!/usr/bin/env python3
"""A tiny LAN clipboard text-sharing page. Run with: python3 clipboard_share.py"""

from datetime import datetime
import errno
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.cookies
import json
import os
from pathlib import PurePosixPath
import re
import secrets
import shutil
import socket
import tempfile
import threading
import time
from urllib.parse import quote, unquote, urlparse
import uuid
import zipfile


HOST = "0.0.0.0"
PORT = 3570
MAX_MESSAGE_BYTES = 200_000
MAX_MESSAGES = 100
MAX_UPLOAD_BYTES = 3 * 1024 * 1024 * 1024
MAX_STORED_BYTES = 3 * 1024 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024
MAX_UPLOAD_BATCHES = 50
MAX_FILES_PER_BATCH = 1000
MAX_UPLOAD_START_BYTES = 1024 * 1024
PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
COOKIE_NAME = "clipshare_session"
AUTH_ATTEMPT_WINDOW = 600
AUTH_ATTEMPT_LIMIT = 10
MAX_SESSIONS = 256
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$", "CLOCK$",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#f5f5f4">
  <title>ClipShare</title>
  <style>
    :root { color-scheme: light dark; font: 16px/1.45 system-ui, sans-serif; }
    body { margin: 0 auto; padding: 20px 14px; max-width: 760px; background: #f5f5f4; color: #202124; }
    h1 { margin: 0 0 4px; font-size: 1.45rem; }
    .sub, #status { color: #62666b; font-size: .9rem; }
    form { margin: 20px 0; }
    textarea { box-sizing: border-box; display: block; width: 100%; min-height: 125px; padding: 12px;
      border: 1px solid #c9cccf; border-radius: 10px; background: white; color: #202124; font: inherit; resize: vertical; }
    button { min-height: 42px; padding: 8px 14px; border: 0; border-radius: 8px; background: #1769d2; color: white;
      font: inherit; font-weight: 600; cursor: pointer; }
    button:disabled { opacity: .55; }
    .send { margin-top: 9px; }
    #status { min-height: 1.4em; margin: 8px 0 18px; }
    #messages { display: grid; gap: 12px; }
    article { padding: 12px; border: 1px solid #dedfdf; border-radius: 10px; background: white; }
    .meta { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; color: #62666b; font-size: .82rem; }
    .copy { min-height: 34px; padding: 5px 11px; background: #e6edf8; color: #174a88; }
    pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
    .empty { color: #62666b; text-align: center; padding: 25px 8px; }
    h2 { margin: 28px 0 4px; font-size: 1.15rem; }
    .file-controls { display: grid; gap: 10px; margin: 12px 0 20px; }
    .picker { display: block; padding: 11px; border: 1px solid #c9cccf; border-radius: 8px; background: white; }
    .picker input { display: block; margin-top: 6px; max-width: 100%; }
    .upload { justify-self: start; }
    #uploads { display: grid; gap: 12px; }
    .download { color: #145ca8; overflow-wrap: anywhere; }
    .file-list { display: grid; gap: 7px; padding-left: 18px; margin: 8px 0 0; }
    .files-meta { color: #62666b; font-size: .82rem; }
    @media (prefers-color-scheme: dark) {
      body { background: #151719; color: #eceff1; }
      .sub, #status, .meta, .empty { color: #aab0b6; }
      textarea, article, .picker { background: #202326; color: #eceff1; border-color: #43484d; }
      .copy { background: #293b50; color: #c7e0ff; }
      .download { color: #9ccaff; }
    }
  </style>
</head>
<body>
  <h1>ClipShare</h1>
  <div class="sub">Paste text below to share it with this PC and other devices on your local network.</div>
  <div class="sub">Only people with the session code shown in the ClipShare app can join. Use this on a trusted network; traffic is not encrypted.</div>
  <form id="form">
    <textarea id="text" placeholder="Paste or type text here…" autofocus></textarea>
    <button class="send" id="send" type="submit">Share text</button>
  </form>
  <div id="status" aria-live="polite"></div>
  <section id="messages" aria-live="polite"></section>
  <h2>Share files or a folder</h2>
  <div class="sub">Up to 1,000 files and 3 GB per upload batch. If your phone browser cannot choose folders, select the files individually or zip the folder first.</div>
  <div class="file-controls">
    <label class="picker">Choose files
      <input id="filePicker" type="file" multiple>
    </label>
    <label class="picker">Choose a folder
      <input id="folderPicker" type="file" webkitdirectory directory multiple>
    </label>
    <button class="upload" id="upload" type="button">Share selected files</button>
  </div>
  <section id="uploads" aria-live="polite"></section>
<script>
  const list = document.querySelector('#messages');
  const uploadsList = document.querySelector('#uploads');
  const status = document.querySelector('#status');
  const input = document.querySelector('#text');
  const MAX_FILES_PER_BATCH = 1000;
  let known = '';
  let knownUploads = '';

  function render(items) {
    const signature = JSON.stringify(items);
    if (signature === known) return;
    known = signature;
    list.replaceChildren();
    if (!items.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = 'Shared text will appear here.';
      list.append(empty);
      return;
    }
    for (const item of items) {
      const card = document.createElement('article');
      const meta = document.createElement('div');
      meta.className = 'meta';
      const label = document.createElement('span');
      label.textContent = `${item.time} · ${item.source}`;
      const copy = document.createElement('button');
      copy.className = 'copy';
      copy.type = 'button';
      copy.textContent = 'Copy';
      copy.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(item.text);
        } catch (_) {
          const helper = document.createElement('textarea');
          helper.value = item.text;
          helper.style.position = 'fixed';
          helper.style.opacity = '0';
          document.body.append(helper);
          helper.select();
          document.execCommand('copy');
          helper.remove();
        }
        status.textContent = 'Copied to this device’s clipboard.';
      });
      const content = document.createElement('pre');
      content.textContent = item.text;
      meta.append(label, copy);
      card.append(meta, content);
      list.append(card);
    }
  }

  function renderUploads(batches) {
    const signature = JSON.stringify(batches);
    if (signature === knownUploads) return;
    knownUploads = signature;
    uploadsList.replaceChildren();
    if (!batches.length) {
      const empty = document.createElement('div');
      empty.className = 'empty';
      empty.textContent = 'Shared files will appear here.';
      uploadsList.append(empty);
      return;
    }
    for (const batch of batches) {
      const card = document.createElement('article');
      const meta = document.createElement('div');
      meta.className = 'meta';
      const label = document.createElement('span');
      label.textContent = `${batch.time} · ${batch.source} · ${batch.files.length} file(s)`;
      const zip = document.createElement('a');
      zip.className = 'download';
      zip.href = `/files/${encodeURIComponent(batch.id)}.zip`;
      zip.textContent = 'Download as ZIP';
      meta.append(label, zip);
      const files = document.createElement('ul');
      files.className = 'file-list';
      for (const file of batch.files) {
        const li = document.createElement('li');
        const link = document.createElement('a');
        link.className = 'download';
        link.href = `/file/${encodeURIComponent(batch.id)}/${encodeURIComponent(file.id)}`;
        link.textContent = file.path;
        li.append(link, ` (${formatSize(file.size)})`);
        files.append(li);
      }
      card.append(meta, files);
      uploadsList.append(card);
    }
  }

  function formatSize(size) {
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }

  async function refresh() {
    try {
      const response = await fetch('/messages', { cache: 'no-store' });
      if (response.ok) render(await response.json());
      const files = await fetch('/files', { cache: 'no-store' });
      if (files.ok) renderUploads(await files.json());
    } catch (_) {
      status.textContent = 'Reconnecting…';
    }
  }

  document.querySelector('#form').addEventListener('submit', async event => {
    event.preventDefault();
    const text = input.value;
    if (!text.trim()) { status.textContent = 'Paste some text first.'; return; }
    const button = document.querySelector('#send');
    button.disabled = true;
    try {
      const response = await fetch('/messages', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not share text.');
      input.value = '';
      status.textContent = 'Shared.';
      await refresh();
    } catch (error) {
      status.textContent = error.message || 'Could not share text.';
    } finally {
      button.disabled = false;
    }
  });

  document.querySelector('#upload').addEventListener('click', async () => {
    const filePicker = document.querySelector('#filePicker');
    const folderPicker = document.querySelector('#folderPicker');
    const selected = [...filePicker.files, ...folderPicker.files];
    if (!selected.length) { status.textContent = 'Choose one or more files or a folder first.'; return; }
    if (selected.length > MAX_FILES_PER_BATCH) {
      status.textContent = `A batch can contain at most ${MAX_FILES_PER_BATCH.toLocaleString()} files.`;
      return;
    }
    const files = selected.map(file => ({name: file.webkitRelativePath || file.name, size: file.size}));
    const button = document.querySelector('#upload');
    button.disabled = true;
    status.textContent = `Preparing ${selected.length} file(s)…`;
    try {
      let response = await fetch('/upload/start', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({files}) });
      let result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not start upload.');
      const uploadId = result.id;
      for (let i = 0; i < selected.length; i++) {
        const file = selected[i];
        for (let offset = 0; offset < file.size; offset += 8 * 1024 * 1024) {
          const chunk = file.slice(offset, Math.min(offset + 8 * 1024 * 1024, file.size));
          response = await fetch(`/upload/${uploadId}/${i}`, {method: 'POST', headers: {'Content-Type': 'application/octet-stream', 'X-Chunk-Offset': String(offset)}, body: chunk});
          result = await response.json();
          if (!response.ok) throw new Error(result.error || 'Could not upload file chunk.');
          status.textContent = `Uploading file ${i + 1}/${selected.length}: ${Math.min(offset + chunk.size, file.size)} / ${file.size} bytes`;
        }
      }
      response = await fetch(`/upload/${uploadId}/finish`, {method: 'POST'});
      result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not finish upload.');
      filePicker.value = '';
      folderPicker.value = '';
      status.textContent = 'Files shared.';
      await refresh();
    } catch (error) {
      status.textContent = error.message || 'Could not upload files.';
    } finally {
      button.disabled = false;
    }
  });

  refresh();
  setInterval(refresh, 1200);
</script>
</body>
</html>
"""


AUTH_PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <title>Join ClipShare</title>
  <style>
    :root { color-scheme: light dark; font: 16px/1.5 system-ui, sans-serif; }
    body { margin: 12vh auto 0; padding: 20px; max-width: 440px; background: #f5f5f4; color: #202124; }
    main { padding: 24px; border: 1px solid #dedfdf; border-radius: 12px; background: white; }
    h1 { margin-top: 0; }
    p { color: #62666b; }
    label { display: block; margin: 18px 0 8px; font-weight: 600; }
    input, button { box-sizing: border-box; width: 100%; min-height: 46px; padding: 10px 12px; border-radius: 8px; font: inherit; }
    input { border: 1px solid #aeb4bb; }
    button { margin-top: 12px; border: 0; background: #1769d2; color: white; font-weight: 600; cursor: pointer; }
    #status { min-height: 1.5em; color: #a52222; }
    @media (prefers-color-scheme: dark) {
      body { background: #151719; color: #eceff1; }
      main, input { background: #202326; color: #eceff1; border-color: #43484d; }
      p { color: #aab0b6; }
    }
  </style>
</head>
<body>
  <main>
    <h1>Join ClipShare</h1>
    <p>Enter the temporary session code shown in the ClipShare window on the host computer.</p>
    <form id="join">
      <label for="code">Session code</label>
      <input id="code" name="code" autocomplete="one-time-code" autocapitalize="characters" required maxlength="14" autofocus>
      <button id="submit" type="submit">Join session</button>
    </form>
    <div id="status" role="status" aria-live="polite"></div>
  </main>
<script>
  document.querySelector('#join').addEventListener('submit', async event => {
    event.preventDefault();
    const button = document.querySelector('#submit');
    const status = document.querySelector('#status');
    button.disabled = true;
    status.textContent = '';
    try {
      const response = await fetch('/auth', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code: document.querySelector('#code').value})
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Could not join this session.');
      window.location.replace('/');
    } catch (error) {
      status.textContent = error.message || 'Could not join this session.';
    } finally {
      button.disabled = false;
    }
  });
</script>
</body>
</html>
"""


class ShareState:
    """Per-session messages, uploads, pairing code, and browser authorizations."""

    def __init__(self, storage_root, pairing_code):
        self.storage_root = storage_root
        self.pairing_code = pairing_code
        self.messages = []
        self.messages_lock = threading.Lock()
        self.upload_batches = []
        self.uploads_lock = threading.Lock()
        self.pending_uploads = {}
        self.stored_bytes = 0
        self.sessions = set()
        self.auth_attempts = {}
        self.auth_lock = threading.Lock()


class ClipShareHTTPServer(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True

    def __init__(self, address, handler, state):
        self.share_state = state
        super().__init__(address, handler)


def local_ip():
    """Find the LAN address selected for outbound traffic without sending data."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


def new_pairing_code():
    raw = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(12))
    return "-".join((raw[:4], raw[4:8], raw[8:]))


def normalize_pairing_code(value):
    return "".join(character for character in value.upper() if character not in "- \t")


def create_session_token():
    return secrets.token_urlsafe(32)


class Handler(BaseHTTPRequestHandler):
    server_version = "ClipShare/1.0"
    timeout = 30

    def log_message(self, fmt, *args):
        # Keep the console quiet; the listening address is printed at startup.
        pass

    @property
    def state(self):
        return self.server.share_state

    def send_body(self, status, content_type, body, headers=()):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "connect-src 'self'; img-src 'self' data:; form-action 'self'; "
            "frame-ancestors 'none'; base-uri 'none'",
        )
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        cookies = http.cookies.SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie", ""))
            token = cookies[COOKIE_NAME].value
        except (KeyError, http.cookies.CookieError):
            return False
        with self.state.auth_lock:
            return token in self.state.sessions

    def require_authorization(self):
        if self.authorized():
            return True
        self.send_body(401, "application/json; charset=utf-8", '{"error":"Enter the session code first."}')
        return False

    def do_auth(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 4096:
            self.send_body(400, "application/json; charset=utf-8", '{"error":"Enter the session code."}')
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            code = payload.get("code") if isinstance(payload, dict) else None
            if not isinstance(code, str):
                raise ValueError
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            self.send_body(400, "application/json; charset=utf-8", '{"error":"Enter the session code."}')
            return

        address = self.client_address[0]
        now = time.monotonic()
        with self.state.auth_lock:
            if address not in self.state.auth_attempts and len(self.state.auth_attempts) >= 4096:
                expired = [
                    peer for peer, (_count, started) in self.state.auth_attempts.items()
                    if now - started >= AUTH_ATTEMPT_WINDOW
                ]
                for peer in expired:
                    self.state.auth_attempts.pop(peer, None)
                if len(self.state.auth_attempts) >= 4096:
                    self.state.auth_attempts.pop(next(iter(self.state.auth_attempts)))
            attempts, first_attempt = self.state.auth_attempts.get(address, (0, now))
            if now - first_attempt >= AUTH_ATTEMPT_WINDOW:
                attempts, first_attempt = 0, now
            if attempts >= AUTH_ATTEMPT_LIMIT:
                self.state.auth_attempts[address] = (attempts, first_attempt)
                self.send_body(429, "application/json; charset=utf-8", '{"error":"Too many tries. Wait a few minutes and try again."}')
                return
            expected = normalize_pairing_code(self.state.pairing_code)
            supplied = normalize_pairing_code(code)
            if not hmac.compare_digest(supplied, expected):
                self.state.auth_attempts[address] = (attempts + 1, first_attempt)
                self.send_body(401, "application/json; charset=utf-8", '{"error":"That session code did not match."}')
                return
            if len(self.state.sessions) >= MAX_SESSIONS:
                self.send_body(429, "application/json; charset=utf-8", '{"error":"This session has reached its device limit."}')
                return
            self.state.auth_attempts.pop(address, None)
            token = create_session_token()
            self.state.sessions.add(token)

        cookie = f"{COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict"
        self.send_body(200, "application/json; charset=utf-8", '{"ok":true}', (("Set-Cookie", cookie),))

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            page = PAGE if self.authorized() else AUTH_PAGE
            self.send_body(200, "text/html; charset=utf-8", page)
        elif not self.require_authorization():
            return
        elif path == "/messages":
            with self.state.messages_lock:
                data = json.dumps(self.state.messages, ensure_ascii=False).encode("utf-8")
            self.send_body(200, "application/json; charset=utf-8", data)
        elif path == "/files":
            with self.state.uploads_lock:
                data = json.dumps(self.state.upload_batches, ensure_ascii=False).encode("utf-8")
            self.send_body(200, "application/json; charset=utf-8", data)
        elif path.startswith("/file/"):
            self.send_file(path)
        elif path.startswith("/files/") and path.endswith(".zip"):
            self.send_zip(path)
        else:
            self.send_body(404, "text/plain; charset=utf-8", "Not found")

    def send_file(self, path):
        parts = [unquote(part) for part in path.split("/")]
        if len(parts) != 4:
            self.send_body(404, "text/plain; charset=utf-8", "Not found")
            return
        batch_id, file_id = parts[2], parts[3]
        with self.state.uploads_lock:
            batch = next((item for item in self.state.upload_batches if item["id"] == batch_id), None)
            file_info = next((item for item in batch["files"] if item["id"] == file_id), None) if batch else None
            file_path = os.path.join(self.state.storage_root, batch_id, file_id) if file_info else None
        if not file_info:
            self.send_body(404, "text/plain; charset=utf-8", "Not found")
            return
        if not os.path.isfile(file_path):
            self.send_body(404, "text/plain; charset=utf-8", "Not found")
            return
        self.send_download_file(file_path, file_info["path"], "application/octet-stream")

    def send_zip(self, path):
        name = unquote(path[len("/files/"):-len(".zip")])
        with self.state.uploads_lock:
            batch = next((item for item in self.state.upload_batches if item["id"] == name), None)
            files = list(batch["files"]) if batch else []
        if not batch:
            self.send_body(404, "text/plain; charset=utf-8", "Not found")
            return
        zip_path = None
        try:
            fd, zip_path = tempfile.mkstemp(prefix="clipshare-", suffix=".zip.tmp", dir=self.state.storage_root)
            os.close(fd)
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for item in files:
                    file_path = os.path.join(self.state.storage_root, batch["id"], item["id"])
                    archive.write(file_path, arcname=item["path"])
        except OSError:
            if zip_path:
                try:
                    os.unlink(zip_path)
                except OSError:
                    pass
            self.send_body(500, "text/plain; charset=utf-8", "Could not create ZIP")
            return
        try:
            self.send_download_file(zip_path, "shared-files.zip", "application/zip")
        finally:
            try: os.unlink(zip_path)
            except OSError: pass

    def send_download(self, data, filename, content_type):
        safe_name = quote(filename.replace("/", "_").replace("\\", "_"), safe="")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{safe_name}")
        self.end_headers()
        self.wfile.write(data)

    def send_download_file(self, path, filename, content_type):
        safe_name = quote(filename.replace("/", "_").replace("\\", "_"), safe="")
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{safe_name}")
        self.end_headers()
        with open(path, "rb") as source:
            shutil.copyfileobj(source, self.wfile, length=1024 * 1024)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/auth":
            self.do_auth()
            return
        if not self.require_authorization():
            return
        if path == "/upload/start":
            self.start_upload()
            return
        if path.startswith("/upload/"):
            self.receive_upload_chunk(path)
            return
        if path != "/messages":
            self.send_body(404, "application/json; charset=utf-8", '{"error":"Not found"}')
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_MESSAGE_BYTES:
            self.send_body(413, "application/json; charset=utf-8", '{"error":"Text is empty or too large (200 KB max)."}')
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            text = payload.get("text") if isinstance(payload, dict) else None
            if not isinstance(text, str) or not text.strip():
                raise ValueError
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, AttributeError):
            self.send_body(400, "application/json; charset=utf-8", '{"error":"Send non-empty text."}')
            return
        if len(text.encode("utf-8")) > MAX_MESSAGE_BYTES:
            self.send_body(413, "application/json; charset=utf-8", '{"error":"Text is too large (200 KB max)."}')
            return
        entry = {
            "text": text,
            "time": datetime.now().astimezone().strftime("%H:%M:%S"),
            "source": self.client_address[0],
        }
        with self.state.messages_lock:
            self.state.messages.append(entry)
            del self.state.messages[:-MAX_MESSAGES]
        self.send_body(201, "application/json; charset=utf-8", '{"ok":true}')

    def start_upload(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_UPLOAD_START_BYTES:
                raise ValueError
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError
            files = payload.get("files", [])
            if not isinstance(files, list) or not files:
                raise ValueError
            if len(files) > MAX_FILES_PER_BATCH:
                self.send_body(
                    413,
                    "application/json; charset=utf-8",
                    json.dumps({"error": f"An upload batch can contain at most {MAX_FILES_PER_BATCH:,} files."}),
                )
                return
            cleaned = []
            seen_names = set()
            for item in files:
                if not isinstance(item, dict):
                    raise ValueError
                name = item.get("name")
                size = item.get("size")
                if not isinstance(name, str) or not isinstance(size, int) or isinstance(size, bool) or size < 0:
                    raise ValueError
                name = name.replace("\\", "/")
                rel = PurePosixPath(name)
                if (
                    rel.is_absolute()
                    or name.startswith("/")
                    or re.match(r"^[A-Za-z]:", name)
                    or ".." in rel.parts
                    or any(ord(character) < 32 or ord(character) == 127 for character in name)
                ):
                    raise ValueError
                normalized = "/".join(part for part in rel.parts if part not in ("", "."))
                components = normalized.split("/")
                if (
                    not normalized
                    or len(normalized) > 1024
                    or normalized in seen_names
                    or any(
                        component.endswith((".", " "))
                        or any(character in '<>:"|?*' for character in component)
                        or component.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES
                        for component in components
                    )
                ):
                    raise ValueError
                seen_names.add(normalized)
                cleaned.append((normalized, size))
            total = sum(size for _name, size in cleaned)
            if total > MAX_UPLOAD_BYTES:
                raise ValueError
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.send_body(400, "application/json; charset=utf-8", '{"error":"Invalid file list or upload exceeds the 3 GB batch limit."}')
            return
        with self.state.uploads_lock:
            pending = sum(item["total"] for item in self.state.pending_uploads.values())
            if len(self.state.upload_batches) + len(self.state.pending_uploads) >= MAX_UPLOAD_BATCHES:
                self.send_body(413, "application/json; charset=utf-8", '{"error":"This session has reached its upload batch limit."}')
                return
            if self.state.stored_bytes + pending + total > MAX_STORED_BYTES:
                self.send_body(413, "application/json; charset=utf-8", '{"error":"The 3 GB temporary storage limit has been reached."}')
                return
            batch_id = uuid.uuid4().hex
            batch_dir = os.path.join(self.state.storage_root, batch_id)
            files = [{"id": uuid.uuid4().hex, "path": name, "size": size, "written": 0} for name, size in cleaned]
            try:
                os.makedirs(batch_dir)
                for item in files:
                    if item["size"] == 0:
                        with open(os.path.join(batch_dir, item["id"]), "xb"):
                            pass
            except OSError:
                shutil.rmtree(batch_dir, ignore_errors=True)
                self.send_body(500, "application/json; charset=utf-8", '{"error":"Could not prepare temporary upload storage."}')
                return
            self.state.pending_uploads[batch_id] = {
                "total": total,
                "files": files,
                "source": self.client_address[0],
                "write_lock": threading.Lock(),
            }
        self.send_body(201, "application/json; charset=utf-8", json.dumps({"id": batch_id}))

    def receive_upload_chunk(self, path):
        parts = path.strip("/").split("/")
        if len(parts) != 3:
            self.send_body(404, "application/json; charset=utf-8", '{"error":"Not found"}'); return
        batch_id, index = parts[1], parts[2]
        if index == "finish":
            self.finish_upload(batch_id); return
        try:
            index = int(index)
            offset = int(self.headers.get("X-Chunk-Offset", "-1"))
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            index, offset, length = -1, -1, -1

        with self.state.uploads_lock:
            pending = self.state.pending_uploads.get(batch_id)
            if not pending or index < 0 or index >= len(pending["files"]):
                upload_lock = None
            else:
                upload_lock = pending["write_lock"]
        if upload_lock is None:
            self.send_body(404, "application/json; charset=utf-8", '{"error":"Upload not found"}')
            return

        # Serialize chunks for this batch, but never hold the session-wide lock
        # while waiting for bytes from a client.
        with upload_lock:
            with self.state.uploads_lock:
                if self.state.pending_uploads.get(batch_id) is not pending:
                    self.send_body(404, "application/json; charset=utf-8", '{"error":"Upload not found"}')
                    return
                item = pending["files"][index]
                if (
                    offset != item["written"]
                    or length <= 0
                    or length > UPLOAD_CHUNK_BYTES
                    or offset + length > item["size"]
                ):
                    self.send_body(400, "application/json; charset=utf-8", '{"error":"Invalid chunk offset or size"}')
                    return
                dest = os.path.join(self.state.storage_root, batch_id, item["id"])

            try:
                chunk = self.rfile.read(length)
            except OSError:
                self.send_body(400, "application/json; charset=utf-8", '{"error":"Upload connection ended before the chunk arrived."}')
                return
            if len(chunk) != length:
                self.send_body(400, "application/json; charset=utf-8", '{"error":"Upload chunk was incomplete; start the upload again."}')
                return
            try:
                with open(dest, "ab") as out:
                    out.write(chunk)
            except OSError:
                self.send_body(500, "application/json; charset=utf-8", '{"error":"Could not save this upload chunk."}')
                return
            item["written"] += length
        self.send_body(200, "application/json; charset=utf-8", '{"ok":true}')

    def finish_upload(self, batch_id):
        with self.state.uploads_lock:
            pending = self.state.pending_uploads.get(batch_id)
            upload_lock = pending["write_lock"] if pending else None
        if upload_lock is None:
            self.send_body(400, "application/json; charset=utf-8", '{"error":"Upload is incomplete"}')
            return

        with upload_lock:
            with self.state.uploads_lock:
                pending = self.state.pending_uploads.get(batch_id)
                if not pending or any(f["written"] != f["size"] for f in pending["files"]):
                    self.send_body(400, "application/json; charset=utf-8", '{"error":"Upload is incomplete"}')
                    return
                files = [{k: f[k] for k in ("id", "path", "size")} for f in pending["files"]]
                self.state.upload_batches.append({"id": batch_id, "time": datetime.now().astimezone().strftime("%H:%M:%S"), "source": pending["source"], "files": files})
                self.state.stored_bytes += pending["total"]
                del self.state.pending_uploads[batch_id]
        self.send_body(201, "application/json; charset=utf-8", '{"ok":true}')


class ShareServer:
    """One temporary sharing session and its HTTP listener."""

    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.requested_port = port
        self.port_fallback = False
        self.temp_storage = tempfile.TemporaryDirectory(prefix="clipshare-")
        self.state = ShareState(self.temp_storage.name, new_pairing_code())
        try:
            self.httpd = ClipShareHTTPServer((host, port), Handler, self.state)
        except OSError as error:
            if port == 0 or (error.errno != errno.EADDRINUSE and getattr(error, "winerror", None) != 10048):
                self.temp_storage.cleanup()
                raise
            try:
                self.httpd = ClipShareHTTPServer((host, 0), Handler, self.state)
            except OSError:
                self.temp_storage.cleanup()
                raise
            self.port_fallback = True
        self.port = self.httpd.server_address[1]
        self.thread = None
        self._stopped = False
        self._stop_lock = threading.Lock()

    def start(self):
        if self.thread is not None:
            raise RuntimeError("This ClipShare session has already been started.")
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="ClipShareHTTP", daemon=False)
        try:
            self.thread.start()
        except RuntimeError:
            self.temp_storage.cleanup()
            self.httpd.server_close()
            raise
        return self

    def stop(self):
        with self._stop_lock:
            if self._stopped:
                return
            if self.thread is not None and self.thread.is_alive():
                self.httpd.shutdown()
                self.thread.join()
            self.httpd.server_close()
            self.temp_storage.cleanup()
            self._stopped = True


def main():
    from .desktop import main as desktop_main

    desktop_main()


if __name__ == "__main__":
    main()
