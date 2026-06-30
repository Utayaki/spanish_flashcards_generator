from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from controllers.drill_question_builder import (
    DRILL_TYPE_META,
    DRILL_TYPES,
    DrillPoolEmptyError,
    build_random_question,
    check_answer,
)
from controllers.verb_form_catalog import build_verb_meta
from database import GENDERS, NUMBERS, DatabaseError, SpanishLexicalItemDatabase, ValidationError

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
            if path == "/api/meta":
                self._api_meta()
            elif path == "/api/drill/random":
                self._api_drill_random(parse_qs(parsed.query))
            elif path == "/api/random":
                self._api_drill_random({"type": ["recognition"]})
            else:
                self._serve_static(path)
        except ApiError as exc:
            self._send_json({"ok": False, "error": str(exc)}, exc.status)
        except DrillPoolEmptyError as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.NOT_FOUND)
        except (ValidationError, DatabaseError, ValueError) as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"ok": False, "error": f"unexpected server error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/drill/check":
                self._api_drill_check()
            else:
                raise ApiError("not found", HTTPStatus.NOT_FOUND)
        except ApiError as exc:
            self._send_json({"ok": False, "error": str(exc)}, exc.status)
        except (ValidationError, DatabaseError, ValueError) as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._send_json({"ok": False, "error": f"unexpected server error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _api_meta(self) -> None:
        verb_meta = build_verb_meta()
        self._send_json(
            {
                "ok": True,
                "drill_types": DRILL_TYPE_META,
                "numbers": [{"value": value, "label": value.capitalize()} for value in NUMBERS],
                "genders": [
                    {"value": "shared", "label": "Shared"},
                    *[{"value": value, "label": value.capitalize()} for value in GENDERS],
                ],
                **verb_meta,
            }
        )

    def _api_drill_random(self, query: dict[str, list[str]]) -> None:
        drill_type = _one(query, "type")
        if drill_type not in DRILL_TYPES:
            raise ApiError(f"invalid drill type: {drill_type}")
        question = build_random_question(DATABASE, drill_type)
        self._send_json({"ok": True, "question": question})

    def _api_drill_check(self) -> None:
        payload = self._read_json()
        result = check_answer(DATABASE, payload)
        self._send_json({"ok": True, **result})

    def _read_json(self) -> dict[str, object]:
        length_text = self.headers.get("Content-Length") or "0"
        try:
            length = int(length_text)
        except ValueError as exc:
            raise ApiError("invalid Content-Length") from exc
        if length > 1_000_000:
            raise ApiError("request is too large", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError as exc:
            raise ApiError(f"invalid JSON: {exc.msg}") from exc
        if not isinstance(data, dict):
            raise ApiError("JSON body must be an object")
        return data

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


def _one(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key)
    if not values:
        raise ApiError(f"missing query parameter: {key}")
    return values[0]


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
