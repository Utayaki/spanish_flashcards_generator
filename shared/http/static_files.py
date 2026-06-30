from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote


def content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
    }.get(suffix, "application/octet-stream")


def serve_static(handler: BaseHTTPRequestHandler, web_dir: Path, path: str) -> None:
    if path in {"", "/"}:
        file_path = web_dir / "index.html"
    else:
        clean_path = unquote(path).lstrip("/")
        candidate = (web_dir / clean_path).resolve()
        if web_dir.resolve() not in candidate.parents and candidate != web_dir.resolve():
            handler.send_error(HTTPStatus.FORBIDDEN.value)
            return
        file_path = candidate
    if not file_path.is_file():
        handler.send_error(HTTPStatus.NOT_FOUND.value)
        return
    body = file_path.read_bytes()
    handler.send_response(HTTPStatus.OK.value)
    handler.send_header("Content-Type", content_type(file_path))
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(body)
