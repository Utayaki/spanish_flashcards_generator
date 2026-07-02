from __future__ import annotations

import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bridge.drill_sync import DrillSyncService
from drill.controllers.drill_service import DrillService
from drill.controllers.question_builder import (
    DRILL_TYPE_META,
    DRILL_TYPES,
    DrillPoolEmptyError,
    build_question_from_card,
    build_random_question,
)
from drill.db import DrillDatabase, default_drill_db_path
from shared.api.drill_answers import answer_schemas_for_meta
from shared.api.drill_requests import (
    parse_check_request,
    parse_create_session_request,
    parse_rate_request,
)
from shared.errors import DatabaseError, ValidationError
from shared.http.errors import ApiError
from shared.http.json_io import read_json_body, send_json
from shared.http.query import one
from shared.http.static_files import serve_static
from shared.verb_form_catalog import build_verb_meta
from word_bank.database import GENDERS, NUMBERS, WordBankDatabase

MAX_JSON_BYTES = 1_000_000

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = Path(__file__).resolve().parent / "web"
DEFAULT_WORD_BANK_DB_PATH = PROJECT_ROOT / "word_bank.db"
WORD_BANK_DB_PATH = Path(os.environ.get("SPANISH_WORD_BANK_DB", DEFAULT_WORD_BANK_DB_PATH))
DRILL_DB_PATH = default_drill_db_path()

WORD_BANK = WordBankDatabase(WORD_BANK_DB_PATH)
DRILL_DB = DrillDatabase(DRILL_DB_PATH)
SYNC = DrillSyncService(WORD_BANK, DRILL_DB)
DRILL_SERVICE = DrillService(WORD_BANK, DRILL_DB)


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
            elif path == "/api/drill/due-count":
                self._api_drill_due_count()
            elif path == "/api/drill/review/next":
                self._api_drill_review_next(parse_qs(parsed.query))
            elif path == "/api/drill/random":
                self._api_drill_random(parse_qs(parsed.query))
            elif path == "/api/random":
                self._api_drill_random({"type": ["recognition"]})
            else:
                serve_static(self, WEB_DIR, path)
        except ApiError as exc:
            send_json(self, {"ok": False, "error": str(exc)}, exc.status)
        except DrillPoolEmptyError as exc:
            send_json(self, {"ok": False, "error": str(exc)}, HTTPStatus.NOT_FOUND)
        except (ValidationError, DatabaseError, ValueError) as exc:
            send_json(self, {"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            send_json(
                self,
                {"ok": False, "error": f"unexpected server error: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/drill/check":
                self._api_drill_check()
            elif path == "/api/drill/review/rate":
                self._api_drill_review_rate()
            elif path == "/api/drill/sessions":
                self._api_create_session()
            elif path.startswith("/api/drill/sessions/") and path.endswith("/finish"):
                session_id = _session_id_from_finish_path(path)
                self._api_finish_session(session_id)
            else:
                raise ApiError("not found", HTTPStatus.NOT_FOUND)
        except ApiError as exc:
            send_json(self, {"ok": False, "error": str(exc)}, exc.status)
        except (ValidationError, DatabaseError, ValueError, LookupError) as exc:
            send_json(self, {"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            send_json(
                self,
                {"ok": False, "error": f"unexpected server error: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _api_meta(self) -> None:
        verb_meta = build_verb_meta()
        send_json(
            self,
            {
                "ok": True,
                "drill_types": DRILL_TYPE_META,
                "numbers": [{"value": value, "label": value.capitalize()} for value in NUMBERS],
                "genders": [
                    {"value": "shared", "label": "Shared"},
                    *[{"value": value, "label": value.capitalize()} for value in GENDERS],
                ],
                **verb_meta,
                "answer_schemas": answer_schemas_for_meta(),
            },
        )

    def _api_drill_stats(self) -> None:
        send_json(
            self,
            {
                "ok": True,
                "stats": DRILL_DB.get_drill_stats_summary(),
                "schedule": DRILL_DB.get_schedule_summary(),
            },
        )

    def _api_drill_due_count(self) -> None:
        DRILL_DB.ensure_all_drill_schedules()
        send_json(self, {"ok": True, **DRILL_DB.get_due_counts()})

    def _api_drill_review_next(self, query: dict[str, list[str]]) -> None:
        drill_type = query.get("type", [None])[0]

        if drill_type is not None and drill_type not in DRILL_TYPES:
            raise ApiError(f"invalid drill type: {drill_type}")

        DRILL_DB.ensure_all_drill_schedules()

        card = DRILL_DB.get_due_drill_card(
            drill_type=drill_type,
            include_new=True,
        )

        if card is None:
            send_json(
                self,
                {
                    "ok": True,
                    "done": True,
                    "question": None,
                    **DRILL_DB.get_due_counts(),
                },
            )
            return

        question = build_question_from_card(WORD_BANK, card)
        question["drill_card_id"] = int(card["id"])
        question["review_mode"] = True

        send_json(
            self,
            {
                "ok": True,
                "done": False,
                "question": question,
                **DRILL_DB.get_due_counts(),
            },
        )

    def _api_drill_review_rate(self) -> None:
        req = parse_rate_request(read_json_body(self, MAX_JSON_BYTES))

        result = DRILL_DB.rate_drill_card(
            drill_card_id=req.drill_card_id,
            drill_attempt_id=req.attempt_id,
            rating_label=req.rating,
            review_duration_ms=req.review_duration_ms,
        )

        send_json(
            self,
            {
                "ok": True,
                **result,
                **DRILL_DB.get_due_counts(),
            },
        )

    def _api_drill_random(self, query: dict[str, list[str]]) -> None:
        drill_type = one(query, "type")
        if drill_type not in DRILL_TYPES:
            raise ApiError(f"invalid drill type: {drill_type}")
        question = build_random_question(WORD_BANK, DRILL_DB, drill_type)
        send_json(self, {"ok": True, "question": question})

    def _api_create_session(self) -> None:
        req = parse_create_session_request(read_json_body(self, MAX_JSON_BYTES))
        session_id = DRILL_DB.create_drill_session(mode=req.mode, drill_type=req.drill_type)
        send_json(self, {"ok": True, "session_id": session_id})

    def _api_finish_session(self, session_id: int) -> None:
        DRILL_DB.finish_drill_session(session_id)
        send_json(self, {"ok": True})

    def _api_drill_check(self) -> None:
        req = parse_check_request(read_json_body(self, MAX_JSON_BYTES))

        result = DRILL_SERVICE.check_card_answer(req.drill_card_id, req.answers)
        attempt_id = DRILL_DB.record_drill_attempt(
            drill_card_id=req.drill_card_id,
            session_id=req.session_id,
            submitted_answer=result.get("submitted_answer", {}),
            expected_answer=result.get("expected_answer", {}),
            result={
                "results": result.get("results", {}),
                "reveal": result.get("reveal", {}),
            },
            is_correct=bool(result["correct"]),
            response_ms=req.response_ms,
        )
        send_json(self, {"ok": True, "attempt_id": attempt_id, **result})


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


def run(host: str = "127.0.0.1", port: int = 8001) -> None:
    card_count = SYNC.sync_all()
    print(f"Synced {card_count} drill card(s) from word bank.")
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
