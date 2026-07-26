from __future__ import annotations

import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from drills.db.database import DrillsDatabase
from drills.errors import DatabaseError
from drills.snapshot import collection_with_item_count, create_collection_from_word_bank
from word_bank.http import ApiError, send_json, serve_static

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "drills.db"
DEFAULT_WORD_BANK_PATH = PROJECT_ROOT / "word_bank.db"
REGISTRY_PATH = Path(os.environ.get("SPANISH_DRILLS_DB", DEFAULT_REGISTRY_PATH))
WORD_BANK_PATH = Path(os.environ.get("SPANISH_WORD_BANK_DB", DEFAULT_WORD_BANK_PATH))

DRILLS_DB = DrillsDatabase(REGISTRY_PATH)


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
        raise ApiError("not found", HTTPStatus.NOT_FOUND)

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
