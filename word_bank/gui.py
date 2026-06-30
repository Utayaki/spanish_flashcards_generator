from __future__ import annotations

import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bridge.drill_sync import DrillSyncService
from drill.db import DrillDatabase, default_drill_db_path
from shared.api.envelope import require_str
from shared.api.word_bank_requests import parse_lexical_item_save
from shared.errors import DatabaseError, ValidationError
from shared.http.errors import ApiError
from shared.http.json_io import read_json_body, send_json
from shared.http.query import one
from shared.http.static_files import serve_static
from shared.verb_form_catalog import build_verb_meta
from word_bank.controllers.noun_editor_state import GENDER_CHOICES
from word_bank.controllers.start_page_presenter import LEXICAL_ITEM_CLASS_META, validate_lexical_item_type
from word_bank.database import GENDERS, NUMBERS, WordBankDatabase

SHARED_GENDER_KEY = "shared"
MAX_JSON_BYTES = 3_000_000

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
DEFAULT_DB_PATH = PROJECT_ROOT / "word_bank.db"
DB_PATH = Path(os.environ.get("SPANISH_WORD_BANK_DB", DEFAULT_DB_PATH))
DRILL_DB_PATH = default_drill_db_path()

WORD_BANK = WordBankDatabase(DB_PATH)
DRILL_DB = DrillDatabase(DRILL_DB_PATH)
SYNC = DrillSyncService(WORD_BANK, DRILL_DB)


class WordBankHandler(BaseHTTPRequestHandler):
    server_version = "SpanishWordBankWeb/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path.startswith("/api/"):
                self._handle_api(method, path, parse_qs(parsed.query))
            elif method == "GET":
                serve_static(self, WEB_DIR, path)
            else:
                raise ApiError("method not allowed", HTTPStatus.METHOD_NOT_ALLOWED)
        except ApiError as exc:
            send_json(self, {"ok": False, "error": str(exc)}, exc.status)
        except (ValidationError, DatabaseError, ValueError) as exc:
            send_json(self, {"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            send_json(
                self,
                {"ok": False, "error": f"unexpected server error: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _handle_api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        if method == "GET" and path == "/api/meta":
            self._api_meta()
            return
        if method == "GET" and path == "/api/search":
            self._api_search(query)
            return
        if method == "POST" and path == "/api/lexical-items":
            self._api_create_lexical_item()
            return
        lexical_item_id = _lexical_item_id_from_path(path)
        if lexical_item_id is None:
            raise ApiError("not found", HTTPStatus.NOT_FOUND)
        if method == "GET":
            self._api_get_lexical_item(lexical_item_id)
        elif method == "PUT":
            self._api_update_lexical_item(lexical_item_id)
        elif method == "DELETE":
            self._api_delete_lexical_item(lexical_item_id)
        else:
            raise ApiError("method not allowed", HTTPStatus.METHOD_NOT_ALLOWED)

    def _api_meta(self) -> None:
        verb_meta = build_verb_meta()
        send_json(
            self,
            {
                "ok": True,
                "lexical_item_types": LEXICAL_ITEM_CLASS_META,
                "lexical_item_type_labels": {
                    item_type: meta["button"] for item_type, meta in LEXICAL_ITEM_CLASS_META.items()
                },
                "gender_choices": [{"value": value, "label": label} for value, label in GENDER_CHOICES],
                "numbers": list(NUMBERS),
                "genders": list(GENDERS),
                "shared_gender_key": SHARED_GENDER_KEY,
                **verb_meta,
                "other_inflection_types": [
                    {"value": "none", "label": "No inflections"},
                    {"value": "plurality", "label": "Plurality"},
                    {"value": "gender_plurality", "label": "Plurality + gender"},
                ],
                "adjective_inflection_types": [
                    {"value": "plurality", "label": "Plurality"},
                    {"value": "gender_plurality", "label": "Plurality + gender"},
                ],
            },
        )

    def _api_search(self, query: dict[str, list[str]]) -> None:
        lexical_item_type = one(query, "lexical_item_type")
        headword = one(query, "q", default="")
        validate_lexical_item_type(lexical_item_type)
        results = WORD_BANK.search_lexical_items(lexical_item_type, headword, limit=10)
        send_json(self, {"ok": True, "results": results})

    def _api_get_lexical_item(self, lexical_item_id: int) -> None:
        send_json(self, {"ok": True, "lexical_item": WORD_BANK.load_lexical_item(lexical_item_id)})

    def _api_create_lexical_item(self) -> None:
        payload = read_json_body(self, MAX_JSON_BYTES)
        lexical_item_type = validate_lexical_item_type(require_str(payload, "lexical_item_type"))
        save = parse_lexical_item_save(lexical_item_type, payload)
        lexical_item_id = save.create(WORD_BANK)
        response: dict[str, object] = {
            "ok": True,
            "lexical_item": WORD_BANK.load_lexical_item(lexical_item_id),
        }
        sync_warning = SYNC.sync_lexical_item_safe(lexical_item_id)
        if sync_warning is not None:
            response["sync_warning"] = sync_warning
        send_json(self, response, HTTPStatus.CREATED)

    def _api_update_lexical_item(self, lexical_item_id: int) -> None:
        existing = WORD_BANK.get_lexical_item_summary(lexical_item_id)
        if existing is None:
            raise ApiError("lexical item not found", HTTPStatus.NOT_FOUND)

        payload = read_json_body(self, MAX_JSON_BYTES)
        lexical_item_type = str(existing["lexical_item_type"])
        submitted_type = payload.get("lexical_item_type")
        if submitted_type is not None and submitted_type != lexical_item_type:
            raise ApiError("changing lexical item type is not supported")

        save = parse_lexical_item_save(lexical_item_type, payload)
        save.update(WORD_BANK, lexical_item_id)
        response: dict[str, object] = {
            "ok": True,
            "lexical_item": WORD_BANK.load_lexical_item(lexical_item_id),
        }
        sync_warning = SYNC.sync_lexical_item_safe(lexical_item_id)
        if sync_warning is not None:
            response["sync_warning"] = sync_warning
        send_json(self, response)

    def _api_delete_lexical_item(self, lexical_item_id: int) -> None:
        if not WORD_BANK.delete_lexical_item(lexical_item_id):
            raise ApiError("lexical item not found", HTTPStatus.NOT_FOUND)
        response: dict[str, object] = {"ok": True}
        sync_warning = SYNC.sync_lexical_item_safe(lexical_item_id)
        if sync_warning is not None:
            response["sync_warning"] = sync_warning
        send_json(self, response)


def _lexical_item_id_from_path(path: str) -> int | None:
    prefix = "/api/lexical-items/"
    if not path.startswith(prefix):
        return None
    raw = path[len(prefix) :].strip("/")
    if not raw or "/" in raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def run(host: str = "127.0.0.1", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), WordBankHandler)
    print(f"Serving Spanish Word Bank at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
