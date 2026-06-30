from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from drill.controllers.question_builder import (
    DRILL_TYPE_META,
    DRILL_TYPES,
    DrillPoolEmptyError,
    build_random_question,
    check_answer,
)
from drill.database import DrillDatabase, default_drill_db_path
from drill.sync import sync_all_drill_cards
from shared.verb_form_catalog import build_verb_meta
from word_bank.database import GENDERS, NUMBERS, DatabaseError, ValidationError, WordBankDatabase

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
DEFAULT_WORD_BANK_DB_PATH = PROJECT_ROOT / "word_bank.db"
WORD_BANK_DB_PATH = Path(os.environ.get("SPANISH_WORD_BANK_DB", DEFAULT_WORD_BANK_DB_PATH))
DRILL_DB_PATH = default_drill_db_path()

WORD_BANK = WordBankDatabase(WORD_BANK_DB_PATH)
DRILL_DB = DrillDatabase(DRILL_DB_PATH)


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
            elif path == "/api/drill/stats":
                self._api_drill_stats()
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
            elif path == "/api/drill/sessions":
                self._api_create_session()
            elif path.startswith("/api/drill/sessions/") and path.endswith("/finish"):
                session_id = _session_id_from_finish_path(path)
                self._api_finish_session(session_id)
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

    def _api_drill_stats(self) -> None:
        self._send_json({"ok": True, "stats": DRILL_DB.get_drill_stats_summary()})

    def _api_drill_random(self, query: dict[str, list[str]]) -> None:
        drill_type = _one(query, "type")
        if drill_type not in DRILL_TYPES:
            raise ApiError(f"invalid drill type: {drill_type}")
        question = build_random_question(WORD_BANK, DRILL_DB, drill_type)
        self._send_json({"ok": True, "question": question})

    def _api_create_session(self) -> None:
        payload = self._read_json()
        mode = str(payload.get("mode", "random"))
        drill_type = payload.get("drill_type")
        if drill_type is not None:
            drill_type = str(drill_type)
            if drill_type not in DRILL_TYPES:
                raise ApiError(f"invalid drill type: {drill_type}")
        session_id = DRILL_DB.create_drill_session(mode=mode, drill_type=drill_type)
        self._send_json({"ok": True, "session_id": session_id})

    def _api_finish_session(self, session_id: int) -> None:
        DRILL_DB.finish_drill_session(session_id)
        self._send_json({"ok": True})

    def _api_drill_check(self) -> None:
        payload = self._read_json()
        drill_card_id = int(payload["drill_card_id"])
        session_id = payload.get("session_id")
        if session_id is not None:
            session_id = int(session_id)

        response_ms_raw = payload.get("response_ms")
        response_ms = int(response_ms_raw) if response_ms_raw is not None else None

        result = check_answer(WORD_BANK, payload)
        attempt_id = DRILL_DB.record_drill_attempt(
            drill_card_id=drill_card_id,
            session_id=session_id,
            submitted_answer=result.get("submitted_answer", {}),
            expected_answer=result.get("expected_answer", {}),
            result={
                "results": result.get("results", {}),
                "reveal": result.get("reveal", {}),
            },
            is_correct=bool(result["correct"]),
            response_ms=response_ms,
        )
        self._send_json({"ok": True, "attempt_id": attempt_id, **result})

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


def _session_id_from_finish_path(path: str) -> int:
    prefix = "/api/drill/sessions/"
    suffix = "/finish"
    if not path.startswith(prefix) or not path.endswith(suffix):
        raise ApiError("not found", HTTPStatus.NOT_FOUND)
    raw = path[len(prefix) : -len(suffix)]
    try:
        return int(raw)
    except ValueError as exc:
        raise ApiError("invalid session id") from exc


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
    sync_all_drill_cards(WORD_BANK, DRILL_DB)
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
