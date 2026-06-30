from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from database import DatabaseError, SpanishLexicalItemDatabase, ValidationError

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "drill_web"
DEFAULT_DB_PATH = APP_DIR / "word_bank.db"
DB_PATH = Path(os.environ.get("SPANISH_WORD_BANK_DB", DEFAULT_DB_PATH))

DATABASE = SpanishLexicalItemDatabase(DB_PATH)


class ApiError(Exception):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


class DrillHandler(BaseHTTPRequestHandler):
    server_version = "SpanishDrillWeb/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/random":
                self._api_random()
            else:
                self._serve_static(path)
        except ApiError as exc:
            self._send_json({"ok": False, "error": str(exc)}, exc.status)
        except (ValidationError, DatabaseError, ValueError) as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"ok": False, "error": f"unexpected server error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _api_random(self) -> None:
        lexical_item = DATABASE.get_random_lexical_item()
        if lexical_item is None:
            raise ApiError("word bank is empty", HTTPStatus.NOT_FOUND)
        self._send_json({"ok": True, "lexical_item": lexical_item})

    def _send_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            file_path = WEB_DIR / "index.html"
        else:
            clean_path = unquote(path).lstrip("/")
            candidate = (WEB_DIR / clean_path).resolve()
            if WEB_DIR.resolve() not in candidate.parents and candidate != WEB_DIR.resolve():
                self.send_error(HTTPStatus.FORBIDDEN.value)
                return
            file_path = candidate
        if not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND.value)
            return
        body = file_path.read_bytes()
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", _content_type(file_path))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)


def _content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".svg": "image/svg+xml",
        ".png": "image/png",
        ".ico": "image/x-icon",
    }.get(suffix, "application/octet-stream")


def run(host: str = "127.0.0.1", port: int = 8001) -> None:
    server = ThreadingHTTPServer((host, port), DrillHandler)
    print(f"Serving Spanish Drill at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
