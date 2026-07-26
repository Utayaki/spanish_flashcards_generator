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
from drills.fsrs.analytics import DEFAULT_DASHBOARD_RANGE_DAYS, validate_range_days
from drills.fsrs.cards import CARD_DIRECTIONS
from drills.inflection.generator import get_job, get_progress, start_generation
from drills.inflection.ollama import OllamaNotRunningError, ensure_ollama_running
from drills.inflection.storage import get_inflection_drill_status
from drills.snapshot import (
    collection_with_item_count,
    create_collection_from_word_bank,
    rename_collection,
)
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
_COLLECTION_PATCH_RE = re.compile(r"^/api/collections/(\d+)$")
_COLLECTION_INFLECTION_RE = re.compile(
    r"^/api/collections/(\d+)/inflection-drills(?:/(?P<action>status|generate(?:/progress)?))?$"
)


def _parse_direction(query: dict[str, list[str]]) -> str:
    values = query.get("direction")
    if not values or not values[0].strip():
        raise ApiError("direction query parameter is required")
    direction = values[0].strip()
    if direction not in CARD_DIRECTIONS:
        raise ApiError(
            f"invalid direction: {direction}; expected one of: {', '.join(sorted(CARD_DIRECTIONS))}"
        )
    return direction


def _parse_timezone_offset(query: dict[str, list[str]]) -> int:
    values = query.get("timezone_offset_minutes")
    if not values or not values[0].strip():
        return 0
    try:
        offset = int(values[0])
    except ValueError as exc:
        raise ApiError("timezone_offset_minutes must be an integer") from exc
    if not -840 <= offset <= 840:
        raise ApiError("timezone_offset_minutes must be between -840 and 840")
    return offset


def _parse_range_days(query: dict[str, list[str]]) -> int:
    values = query.get("range_days")
    if not values or not values[0].strip():
        return DEFAULT_DASHBOARD_RANGE_DAYS
    try:
        range_days = int(values[0])
    except ValueError as exc:
        raise ApiError("range_days must be an integer") from exc
    try:
        return validate_range_days(range_days)
    except ValueError as exc:
        raise ApiError(str(exc)) from exc


def _parse_direction_body(body: dict) -> str:
    direction = body.get("direction")
    if not isinstance(direction, str) or not direction.strip():
        raise ApiError("direction must be a non-empty string")
    direction = direction.strip()
    if direction not in CARD_DIRECTIONS:
        raise ApiError(
            f"invalid direction: {direction}; expected one of: {', '.join(sorted(CARD_DIRECTIONS))}"
        )
    return direction


class DrillsHandler(BaseHTTPRequestHandler):
    server_version = "SpanishDrillsWeb/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch("PATCH")

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
        if method == "GET" and path == "/api/collections":
            self._api_list_collections()
            return
        if method == "POST" and path == "/api/collections":
            self._api_create_collection()
            return

        patch_match = _COLLECTION_PATCH_RE.match(path)
        if patch_match and method == "PATCH":
            self._api_rename_collection(int(patch_match.group(1)))
            return

        match = _COLLECTION_ID_RE.match(path)
        if match:
            collection_id = int(match.group(1))
            action = match.group("action")
            if method == "GET" and action == "stats":
                self._api_fsrs_stats(collection_id, query)
                return
            if method == "GET" and action == "next":
                self._api_fsrs_next(collection_id, query)
                return
            if method == "POST" and action == "rate":
                self._api_fsrs_rate(collection_id)
                return
            if method == "POST" and action == "optimize":
                self._api_fsrs_optimize(collection_id)
                return

        inflection_match = _COLLECTION_INFLECTION_RE.match(path)
        if inflection_match:
            collection_id = int(inflection_match.group(1))
            action = inflection_match.group("action")
            if method == "GET" and action == "status":
                self._api_inflection_drills_status(collection_id)
                return
            if method == "POST" and action == "generate":
                self._api_inflection_drills_generate(collection_id)
                return
            if method == "GET" and action == "generate/progress":
                self._api_inflection_drills_progress(collection_id)
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

    def _snapshot_path(self, collection_id: int) -> Path:
        collection = self._get_collection_or_raise(collection_id)
        return PROJECT_ROOT / str(collection["snapshot_path"])

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

    def _api_rename_collection(self, collection_id: int) -> None:
        body = read_json_body(self, MAX_JSON_BYTES)
        display_name = body.get("display_name")
        if not isinstance(display_name, str):
            display_name = body.get("name")
        if not isinstance(display_name, str):
            raise ApiError("display_name must be a string")
        collection = rename_collection(
            collection_id,
            display_name,
            DRILLS_DB,
            project_root=PROJECT_ROOT,
        )
        send_json(self, {"ok": True, "collection": collection})

    def _api_fsrs_stats(self, collection_id: int, query: dict[str, list[str]]) -> None:
        direction = _parse_direction(query)
        snapshot = self._open_snapshot(collection_id)
        dashboard = snapshot.get_stats(
            direction,
            timezone_offset_minutes=_parse_timezone_offset(query),
            range_days=_parse_range_days(query),
        )
        send_json(
            self,
            {
                "ok": True,
                "stats": dashboard["counts"],
                "analytics": dashboard["analytics"],
            },
        )

    def _api_fsrs_next(self, collection_id: int, query: dict[str, list[str]]) -> None:
        direction = _parse_direction(query)
        snapshot = self._open_snapshot(collection_id)
        card = snapshot.get_next(direction)
        if card is None:
            stats = snapshot.get_counts(direction)
            send_json(self, {"ok": True, "done": True, "stats": stats})
            return
        send_json(self, {"ok": True, "card": card})

    def _api_fsrs_rate(self, collection_id: int) -> None:
        body = read_json_body(self, MAX_JSON_BYTES)
        direction = _parse_direction_body(body)
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
            direction=direction,
            study_card_id=study_card_id,
            rating=rating,
            review_duration_ms=duration,
        )
        send_json(self, {"ok": True, "result": result})

    def _api_fsrs_optimize(self, collection_id: int) -> None:
        snapshot = self._open_snapshot(collection_id)
        result = snapshot.optimize()
        send_json(self, {"ok": True, "result": result})

    def _api_inflection_drills_status(self, collection_id: int) -> None:
        snapshot_path = self._snapshot_path(collection_id)
        status = get_inflection_drill_status(snapshot_path)
        progress = get_progress(collection_id)
        send_json(
            self,
            {
                "ok": True,
                "status": status,
                "generating": progress["generating"],
                "progress": progress,
            },
        )

    def _api_inflection_drills_generate(self, collection_id: int) -> None:
        existing = get_job(collection_id)
        if existing is not None and existing.progress.generating:
            raise ApiError("inflection drill generation already in progress", HTTPStatus.CONFLICT)

        try:
            ensure_ollama_running()
        except OllamaNotRunningError as exc:
            raise ApiError(str(exc), HTTPStatus.SERVICE_UNAVAILABLE) from exc

        snapshot_path = self._snapshot_path(collection_id)
        start_generation(collection_id, snapshot_path)
        send_json(
            self,
            {
                "ok": True,
                "generating": True,
                "progress": get_progress(collection_id),
            },
            HTTPStatus.ACCEPTED,
        )

    def _api_inflection_drills_progress(self, collection_id: int) -> None:
        send_json(self, {"ok": True, "progress": get_progress(collection_id)})


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
