#!/usr/bin/env python3
"""A tiny LAN clipboard text-sharing page. Run with: python3 clipboard_share.py"""

from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import PurePosixPath
import shutil
import signal
import socket
import tempfile
import threading
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
messages = []
messages_lock = threading.Lock()
upload_batches = []
uploads_lock = threading.Lock()
storage_root = None
pending_uploads = {}
stored_bytes = 0


PAGE = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#f5f5f4">
  <title>Clipboard Share</title>
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
  <h1>Clipboard Share</h1>
  <div class="sub">Paste text below to share it with this PC and other devices on your Wi-Fi.</div>
  <form id="form">
    <textarea id="text" placeholder="Paste or type text here…" autofocus></textarea>
    <button class="send" id="send" type="submit">Share text</button>
  </form>
  <div id="status" aria-live="polite"></div>
  <section id="messages" aria-live="polite"></section>
  <h2>Share files or a folder</h2>
  <div class="sub">Up to 3 GB per upload batch. If your phone browser cannot choose folders, select the files individually or zip the folder first.</div>
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


def local_ip():
    """Find the LAN address selected for outbound traffic without sending data."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))
        return sock.getsockname()[0]
    except OSError:
        return "<PC-LAN-IP>"
    finally:
        sock.close()


class Handler(BaseHTTPRequestHandler):
    server_version = "ClipboardShare/1.0"

    def log_message(self, fmt, *args):
        # Keep the console quiet; the listening address is printed at startup.
        pass

    def send_body(self, status, content_type, body):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            self.send_body(200, "text/html; charset=utf-8", PAGE)
        elif path == "/messages":
            with messages_lock:
                data = json.dumps(messages, ensure_ascii=False).encode("utf-8")
            self.send_body(200, "application/json; charset=utf-8", data)
        elif path == "/files":
            with uploads_lock:
                data = json.dumps(upload_batches, ensure_ascii=False).encode("utf-8")
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
        with uploads_lock:
            batch = next((item for item in upload_batches if item["id"] == batch_id), None)
            file_info = next((item for item in batch["files"] if item["id"] == file_id), None) if batch else None
            file_path = os.path.join(storage_root, batch_id, file_id) if file_info else None
        if not file_info:
            self.send_body(404, "text/plain; charset=utf-8", "Not found")
            return
        try:
            with open(file_path, "rb") as uploaded:
                data = uploaded.read()
        except OSError:
            self.send_body(404, "text/plain; charset=utf-8", "Not found")
            return
        self.send_download_file(file_path, file_info["path"], "application/octet-stream")

    def send_zip(self, path):
        name = unquote(path[len("/files/"):-len(".zip")])
        with uploads_lock:
            batch = next((item for item in upload_batches if item["id"] == name), None)
            files = list(batch["files"]) if batch else []
        if not batch:
            self.send_body(404, "text/plain; charset=utf-8", "Not found")
            return
        zip_path = os.path.join(storage_root, f"{name}.zip.tmp")
        try:
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as archive:
                for item in files:
                    file_path = os.path.join(storage_root, batch["id"], item["id"])
                    archive.write(file_path, arcname=item["path"])
        except OSError:
            try: os.unlink(zip_path)
            except OSError: pass
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
        with messages_lock:
            messages.append(entry)
            del messages[:-MAX_MESSAGES]
        self.send_body(201, "application/json; charset=utf-8", '{"ok":true}')

    def start_upload(self):
        global stored_bytes
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            files = payload.get("files", [])
            total = sum(int(item["size"]) for item in files)
            if not files or total < 0 or total > MAX_UPLOAD_BYTES:
                raise ValueError
            cleaned = []
            for item in files:
                name = str(item["name"]).replace("\\", "/")
                rel = PurePosixPath(name)
                if rel.is_absolute() or ".." in rel.parts: raise ValueError
                cleaned.append(("/".join(p for p in rel.parts if p not in ("", ".")), int(item["size"])))
            if any(not name for name, _ in cleaned): raise ValueError
        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.send_body(400, "application/json; charset=utf-8", '{"error":"Invalid file list or upload exceeds 3 GB."}')
            return
        with uploads_lock:
            pending = sum(item["total"] for item in pending_uploads.values())
            if stored_bytes + pending + total > MAX_STORED_BYTES:
                self.send_body(413, "application/json; charset=utf-8", '{"error":"The 3 GB temporary storage limit has been reached."}')
                return
            batch_id = uuid.uuid4().hex
            batch_dir = os.path.join(storage_root, batch_id)
            os.makedirs(batch_dir)
            pending_uploads[batch_id] = {"total": total, "files": [{"id": uuid.uuid4().hex, "path": n, "size": s, "written": 0} for n, s in cleaned], "source": self.client_address[0]}
        self.send_body(201, "application/json; charset=utf-8", json.dumps({"id": batch_id}))

    def receive_upload_chunk(self, path):
        parts = path.strip("/").split("/")
        if len(parts) != 3:
            self.send_body(404, "application/json; charset=utf-8", '{"error":"Not found"}'); return
        batch_id, index = parts[1], parts[2]
        if index == "finish":
            self.finish_upload(batch_id); return
        try: index = int(index); offset = int(self.headers.get("X-Chunk-Offset", "-1")); length = int(self.headers.get("Content-Length", "0"))
        except ValueError: index, offset, length = -1, -1, -1
        with uploads_lock:
            pending = pending_uploads.get(batch_id)
            if not pending or index < 0 or index >= len(pending["files"]):
                self.send_body(404, "application/json; charset=utf-8", '{"error":"Upload not found"}'); return
            item = pending["files"][index]
            if offset != item["written"] or length <= 0 or length > UPLOAD_CHUNK_BYTES or offset + length > item["size"]:
                self.send_body(400, "application/json; charset=utf-8", '{"error":"Invalid chunk offset or size"}'); return
            dest = os.path.join(storage_root, batch_id, item["id"])
            with open(dest, "ab") as out:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk: raise OSError("incomplete chunk")
                    out.write(chunk); remaining -= len(chunk)
            item["written"] += length
        self.send_body(200, "application/json; charset=utf-8", '{"ok":true}')

    def finish_upload(self, batch_id):
        global stored_bytes
        with uploads_lock:
            pending = pending_uploads.get(batch_id)
            if not pending or any(f["written"] != f["size"] for f in pending["files"]):
                self.send_body(400, "application/json; charset=utf-8", '{"error":"Upload is incomplete"}'); return
            files = [{k: f[k] for k in ("id", "path", "size")} for f in pending["files"]]
            upload_batches.append({"id": batch_id, "time": datetime.now().astimezone().strftime("%H:%M:%S"), "source": pending["source"], "files": files})
            stored_bytes += pending["total"]; del pending_uploads[batch_id]
        self.send_body(201, "application/json; charset=utf-8", '{"ok":true}')


def main():
    global storage_root
    temp_storage = tempfile.TemporaryDirectory(prefix="clipboard-share-")
    storage_root = temp_storage.name
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Clipboard Share is running. On this PC: http://localhost:{PORT}")
    print(f"On your phone:          http://{local_ip()}:{PORT}")
    print("Keep this terminal open; press Ctrl+C to stop. Shared messages are kept in memory.")

    def request_shutdown(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, request_shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Clipboard Share.")
    finally:
        server.server_close()
        temp_storage.cleanup()


if __name__ == "__main__":
    main()
