from __future__ import annotations

import os
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bridge.drill_sync import DrillSyncService
from drill.db import DrillDatabase, default_drill_db_path
from shared.errors import DatabaseError, ValidationError
from shared.http.errors import ApiError
from shared.http.json_io import read_json_body, send_json
from shared.http.query import one
from shared.http.static_files import serve_static
from shared.verb_form_catalog import build_verb_meta
from word_bank.controllers.adjective_editor_state import AdjectiveSavePayload
from word_bank.controllers.noun_editor_state import GENDER_CHOICES, NounSavePayload
from word_bank.controllers.other_editor_state import OtherSavePayload
from word_bank.controllers.start_page_presenter import LEXICAL_ITEM_CLASS_META, validate_lexical_item_type
from word_bank.controllers.verb_editor_state import VerbSavePayload
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

LexicalItemSavePayload = NounSavePayload | AdjectiveSavePayload | OtherSavePayload | VerbSavePayload


def empty_gendered_forms() -> dict[tuple[str, str | None], str | None]:
    return {(number, gender): None for number in NUMBERS for gender in GENDERS}


def empty_shared_forms() -> dict[tuple[str, str | None], str | None]:
    return {(number, None): None for number in NUMBERS}


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
        lexical_item_type = validate_lexical_item_type(_required_str(payload, "lexical_item_type"))
        save = _payload_from_request(lexical_item_type, payload)
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

        save = _payload_from_request(lexical_item_type, payload)
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


def _parse_noun_payload(payload: dict[str, object]) -> NounSavePayload:
    return NounSavePayload.from_inputs(
        headword=_required_str(payload, "headword"),
        explanation=_required_str(payload, "explanation"),
        gender_availability=_required_str(payload, "gender_availability"),
        forms=_forms_from_payload(payload.get("forms"), include_shared=False),
    )


def _parse_adjective_payload(payload: dict[str, object]) -> AdjectiveSavePayload:
    return AdjectiveSavePayload.from_inputs(
        headword=_required_str(payload, "headword"),
        explanation=_required_str(payload, "explanation"),
        inflection_type=_adjective_type_from_payload(payload),
        forms=_forms_from_payload(payload.get("forms"), include_shared=True),
    )


def _parse_other_payload(payload: dict[str, object]) -> OtherSavePayload:
    return OtherSavePayload.from_inputs(
        headword=_required_str(payload, "headword"),
        explanation=_required_str(payload, "explanation"),
        inflection_type=_required_str(payload, "inflection_type"),
        forms=_forms_from_payload(payload.get("forms"), include_shared=True),
    )


def _parse_verb_payload(payload: dict[str, object]) -> VerbSavePayload:
    return VerbSavePayload.from_inputs(
        headword=_required_str(payload, "headword"),
        explanation=_required_str(payload, "explanation"),
        forms=_verb_forms_from_payload(payload.get("forms")),
    )


_PAYLOAD_PARSERS: dict[str, Callable[[dict[str, object]], LexicalItemSavePayload]] = {
    "noun": _parse_noun_payload,
    "adjective": _parse_adjective_payload,
    "other": _parse_other_payload,
    "verb": _parse_verb_payload,
}


def _payload_from_request(lexical_item_type: str, payload: dict[str, object]) -> LexicalItemSavePayload:
    parser = _PAYLOAD_PARSERS.get(lexical_item_type)
    if parser is None:
        raise ApiError(f"unsupported lexical item type: {lexical_item_type}")
    return parser(payload)


def _required_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if value is None:
        raise ApiError(f"missing field: {key}")
    if not isinstance(value, str):
        raise ApiError(f"field must be a string: {key}")
    return value


def _adjective_type_from_payload(payload: dict[str, object]) -> str:
    value = payload.get("adjective_inflection_type", "gender_plurality")
    if not isinstance(value, str):
        raise ApiError("adjective_inflection_type must be a string")
    return value


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


def _forms_from_payload(raw: object, *, include_shared: bool) -> dict[tuple[str, str | None], str | None]:
    forms = empty_gendered_forms()
    if include_shared:
        forms.update(empty_shared_forms())
    if raw is None:
        return forms
    if not isinstance(raw, dict):
        raise ApiError("forms must be an object")
    for number in NUMBERS:
        number_map = raw.get(number, {})
        if number_map is None:
            continue
        if not isinstance(number_map, dict):
            raise ApiError(f"forms.{number} must be an object")
        for gender in GENDERS:
            value = number_map.get(gender)
            if value is not None and not isinstance(value, str):
                raise ApiError(f"forms.{number}.{gender} must be a string or null")
            forms[(number, gender)] = value
        if include_shared:
            value = number_map.get(SHARED_GENDER_KEY)
            if value is not None and not isinstance(value, str):
                raise ApiError(f"forms.{number}.{SHARED_GENDER_KEY} must be a string or null")
            forms[(number, None)] = value
    return forms


def _verb_forms_from_payload(raw: object) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    if raw is None:
        return result
    if not isinstance(raw, dict):
        raise ApiError("forms must be an object")
    for code, payload in raw.items():
        if not isinstance(code, str):
            raise ApiError("verb form keys must be strings")
        result[code] = _form_payload(payload, f"forms.{code}")
    return result


def _form_payload(raw: object, field: str) -> dict[str, object]:
    if raw is None:
        return {"form": None}
    if isinstance(raw, str):
        return {"form": raw}
    if isinstance(raw, dict):
        form = raw.get("form")
        if form is not None and not isinstance(form, str):
            raise ApiError(f"{field}.form must be a string or null")
        return {"form": form}
    raise ApiError(f"{field} must be a string, null, or object")


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
