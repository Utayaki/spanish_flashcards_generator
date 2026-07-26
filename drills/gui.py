from __future__ import annotations

import os
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from drills.collection_snapshot import open_collection_snapshot
from drills.db.database import DrillsDatabase
from drills.errors import DatabaseError
from drills.snapshot import collection_with_item_count, create_collection_from_word_bank
from word_bank.http import ApiError, read_json_body, send_json, serve_static

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "drills.db"
DEFAULT_WORD_BANK_PATH = PROJECT_ROOT / "word_bank.db"
REGISTRY_PATH = Path(os.environ.get("SPANISH_DRILLS_DB", DEFAULT_REGISTRY_PATH))
WORD_BANK_PATH = Path(os.environ.get("SPANISH_WORD_BANK_DB", DEFAULT_WORD_BANK_PATH))
MAX_JSON_BYTES = 64 * 1024

DRILLS_DB = DrillsDatabase(REGISTRY_PATH)

_COLLECTION_ID_RE = re.compile(r"^/api/collections/(\d+)(?:/fsrs(?:/(?P<action>stats|next|rate|optimize))?)?$")


class DrillsHandler(BaseHTTPRequestHandler):
    server_version = "SpanishDrillsWeb/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

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
        except (DatabaseError, ValueError) as exc:
            send_json(self, {"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            send_json(
                self,
                {"ok": False, "error": f"unexpected server error: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def _handle_api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        del query
        if method == "GET" and path == "/api/collections":
            self._api_list_collections()
            return
        if method == "POST" and path == "/api/collections":
            self._api_create_collection()
            return

        match = _COLLECTION_ID_RE.match(path)
        if match:
            collection_id = int(match.group(1))
            action = match.group("action")
            if method == "GET" and action == "stats":
                self._api_fsrs_stats(collection_id)
                return
            if method == "GET" and action == "next":
                self._api_fsrs_next(collection_id)
                return
            if method == "POST" and action == "rate":
                self._api_fsrs_rate(collection_id)
                return
            if method == "POST" and action == "optimize":
                self._api_fsrs_optimize(collection_id)
                return

        raise ApiError("not found", HTTPStatus.NOT_FOUND)

    def _get_collection_or_raise(self, collection_id: int) -> dict:
        collection = DRILLS_DB.get_collection(collection_id)
        if collection is None:
            raise ApiError("collection not found", HTTPStatus.NOT_FOUND)
        return collection

    def _open_snapshot(self, collection_id: int):
        collection = self._get_collection_or_raise(collection_id)
        return open_collection_snapshot(collection, project_root=PROJECT_ROOT)

    def _api_list_collections(self) -> None:
        collections = [
            collection_with_item_count(row, project_root=PROJECT_ROOT)
            for row in DRILLS_DB.list_collections()
        ]
        send_json(self, {"ok": True, "collections": collections})

    def _api_create_collection(self) -> None:
        collection = create_collection_from_word_bank(
            WORD_BANK_PATH,
            DRILLS_DB,
            project_root=PROJECT_ROOT,
        )
        send_json(self, {"ok": True, "collection": collection}, HTTPStatus.CREATED)

    def _api_fsrs_stats(self, collection_id: int) -> None:
        snapshot = self._open_snapshot(collection_id)
        stats = snapshot.get_stats()
        send_json(self, {"ok": True, "stats": stats})

    def _api_fsrs_next(self, collection_id: int) -> None:
        snapshot = self._open_snapshot(collection_id)
        card = snapshot.get_next()
        if card is None:
            stats = snapshot.get_stats()
            send_json(self, {"ok": True, "done": True, "stats": stats})
            return
        send_json(self, {"ok": True, "card": card})

    def _api_fsrs_rate(self, collection_id: int) -> None:
        body = read_json_body(self, MAX_JSON_BYTES)
        study_card_id = body.get("study_card_id")
        rating = body.get("rating")
        review_duration_ms = body.get("review_duration_ms")

        if not isinstance(study_card_id, int):
            raise ApiError("study_card_id must be an integer")
        if not isinstance(rating, str):
            raise ApiError("rating must be a string")

        duration: int | None
        if review_duration_ms is None:
            duration = None
        elif isinstance(review_duration_ms, int) and review_duration_ms >= 0:
            duration = review_duration_ms
        else:
            raise ApiError("review_duration_ms must be a non-negative integer or null")

        snapshot = self._open_snapshot(collection_id)
        result = snapshot.rate(
            study_card_id=study_card_id,
            rating=rating,
            review_duration_ms=duration,
        )
        send_json(self, {"ok": True, "result": result})

    def _api_fsrs_optimize(self, collection_id: int) -> None:
        snapshot = self._open_snapshot(collection_id)
        result = snapshot.optimize()
        send_json(self, {"ok": True, "result": result})


def run(host: str = "127.0.0.1", port: int = 8001) -> None:
    server = ThreadingHTTPServer((host, port), DrillsHandler)
    print(f"Serving Spanish Drills at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
