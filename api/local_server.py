from __future__ import annotations

import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from lambda_api import handler

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


class Handler(BaseHTTPRequestHandler):
    def _write(self, status: int, body: bytes, content_type: str):
        self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(body)

    def do_OPTIONS(self): self._write(204, b"", "text/plain")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api"):
            event={"httpMethod":"GET","path":parsed.path[4:] or "/","headers":dict(self.headers)}
            if event["path"].startswith("//"): event["path"]=event["path"][1:]
            result=handler(event, None); self._write(result["statusCode"], result["body"].encode(), "application/json"); return
        path = parsed.path.lstrip("/") or "index.html"
        target = (FRONTEND / path).resolve()
        if FRONTEND not in target.parents and target != FRONTEND: self._write(403, b"Forbidden", "text/plain"); return
        if not target.exists(): target = FRONTEND / "index.html"
        self._write(200, target.read_bytes(), mimetypes.guess_type(target.name)[0] or "application/octet-stream")

    def do_POST(self):
        parsed=urlparse(self.path)
        if not parsed.path.startswith("/api"):
            self._write(404,b"Not found","text/plain"); return
        length=int(self.headers.get("Content-Length",0)); raw=self.rfile.read(length).decode() if length else "{}"
        event={"httpMethod":"POST","path":parsed.path[4:] or "/","headers":dict(self.headers),"body":raw}
        if event["path"].startswith("//"): event["path"]=event["path"][1:]
        result=handler(event,None); self._write(result["statusCode"], result["body"].encode(), "application/json")


if __name__ == "__main__":
    port=int(os.getenv("PORT","8080")); print(f"OpsRelay local server: http://localhost:{port}"); ThreadingHTTPServer(("0.0.0.0",port),Handler).serve_forever()
