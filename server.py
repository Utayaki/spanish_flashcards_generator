from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from controllers.nominal_editor_state import GENDER_CHOICES, NominalSavePayload
from controllers.other_editor_state import OtherSavePayload
from controllers.start_page_presenter import WORD_CLASS_META, validate_word_type
from controllers.verb_editor_state import (
    PARTICIPLE_LABELS,
    PARTICIPLE_TYPES,
    VERB_GROUP_LABELS,
    VerbSavePayload,
    group_tenses,
    ordered_persons,
)
from database import DatabaseError, SpanishWordDatabase, ValidationError
from widgets.form_state import GENDERS, NUMBERS, empty_nominal_forms

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
STATIC_DIR = WEB_DIR / "static"
DEFAULT_DB_PATH = APP_DIR / "spanish_words.db"
DB_PATH = Path(os.environ.get("SPANISH_FLASHCARDS_DB", DEFAULT_DB_PATH))

DATABASE = SpanishWordDatabase(DB_PATH)


class ApiError(Exception):
    def __init__(self, message: str, status: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.status = status


class FlashcardsHandler(BaseHTTPRequestHandler):
    server_version = "SpanishFlashcardsWeb/1.0"

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep console output useful: one compact access line per request.
        print(f"{self.address_string()} - {fmt % args}")

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path.startswith("/api/"):
                self._handle_api(method, path, parse_qs(parsed.query))
            elif method == "GET":
                self._serve_static(path)
            else:
                raise ApiError("method not allowed", HTTPStatus.METHOD_NOT_ALLOWED)
        except ApiError as exc:
            self._send_json({"ok": False, "error": str(exc)}, exc.status)
        except (ValidationError, DatabaseError, ValueError) as exc:
            self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # Defensive: never return a broken HTML traceback to the UI.
            self._send_json({"ok": False, "error": f"unexpected server error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        if method == "GET" and path == "/api/meta":
            self._api_meta()
            return
        if method == "GET" and path == "/api/search":
            self._api_search(query)
            return
        if method == "POST" and path == "/api/words":
            self._api_create_word()
            return
        word_id = _word_id_from_path(path)
        if word_id is None:
            raise ApiError("not found", HTTPStatus.NOT_FOUND)
        if method == "GET":
            self._api_get_word(word_id)
        elif method == "PUT":
            self._api_update_word(word_id)
        elif method == "DELETE":
            self._api_delete_word(word_id)
        else:
            raise ApiError("method not allowed", HTTPStatus.METHOD_NOT_ALLOWED)

    def _api_meta(self) -> None:
        tenses = group_tenses(DATABASE.list_verb_tenses())
        persons = ordered_persons(DATABASE.list_verb_persons())
        verb_groups = [
            {
                "code": group_code,
                "label": VERB_GROUP_LABELS[group_code],
                "tenses": tenses[group_code],
            }
            for group_code in tenses
        ]
        self._send_json(
            {
                "ok": True,
                "word_types": WORD_CLASS_META,
                "gender_choices": [{"value": value, "label": label} for value, label in GENDER_CHOICES],
                "numbers": list(NUMBERS),
                "genders": list(GENDERS),
                "participle_types": [
                    {"value": value, "label": PARTICIPLE_LABELS[value]} for value in PARTICIPLE_TYPES
                ],
                "verb_groups": verb_groups,
                "persons": persons,
            }
        )

    def _api_search(self, query: dict[str, list[str]]) -> None:
        word_type = _one(query, "word_type")
        lemma = _one(query, "q", default="")
        validate_word_type(word_type)
        results = DATABASE.search_words(word_type, lemma, limit=10)
        self._send_json({"ok": True, "results": results})

    def _api_get_word(self, word_id: int) -> None:
        self._send_json({"ok": True, "word": DATABASE.load_word(word_id)})

    def _api_create_word(self) -> None:
        payload = self._read_json()
        word_type = validate_word_type(_required_str(payload, "word_type"))
        if word_type in {"noun", "adjective"}:
            save = NominalSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                gender_availability=_required_str(payload, "gender_availability"),
                forms=_nominal_forms_from_payload(payload.get("forms")),
            )
            word_id = DATABASE.create_nominal_word(
                lemma=save.lemma,
                word_type=word_type,
                english=save.english,
                gender_availability=save.gender_availability,
                forms=save.forms,
            )
        elif word_type == "other":
            save = OtherSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                has_inflections=bool(payload.get("has_inflections")),
                forms=_nominal_forms_from_payload(payload.get("forms")),
            )
            word_id = DATABASE.create_other_word(
                lemma=save.lemma,
                english=save.english,
                has_inflections=save.has_inflections,
                forms=save.forms,
            )
        else:
            save = VerbSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                participles=_participles_from_payload(payload.get("participles")),
                forms=_verb_forms_from_payload(payload.get("forms")),
            )
            word_id = DATABASE.create_verb_word(
                lemma=save.lemma,
                english=save.english,
                participles=save.participles,
                forms=save.forms,
            )
        self._send_json({"ok": True, "word": DATABASE.load_word(word_id)}, HTTPStatus.CREATED)

    def _api_update_word(self, word_id: int) -> None:
        existing = DATABASE.get_word_summary(word_id)
        if existing is None:
            raise ApiError("word not found", HTTPStatus.NOT_FOUND)
        payload = self._read_json()
        word_type = str(existing["word_type"])
        submitted_type = payload.get("word_type")
        if submitted_type is not None and submitted_type != word_type:
            raise ApiError("changing word type is not supported")

        if word_type in {"noun", "adjective"}:
            save = NominalSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                gender_availability=_required_str(payload, "gender_availability"),
                forms=_nominal_forms_from_payload(payload.get("forms")),
            )
            DATABASE.save_word_base(word_id, lemma=save.lemma, english=save.english)
            DATABASE.save_nominal_details(word_id, save.gender_availability)
            DATABASE.save_nominal_inflections(word_id, save.forms)
        elif word_type == "other":
            save = OtherSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                has_inflections=bool(payload.get("has_inflections")),
                forms=_nominal_forms_from_payload(payload.get("forms")),
            )
            DATABASE.save_word_base(word_id, lemma=save.lemma, english=save.english)
            DATABASE.save_other_details(word_id, save.has_inflections)
            DATABASE.save_other_inflections(word_id, save.forms)
        elif word_type == "verb":
            save = VerbSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                participles=_participles_from_payload(payload.get("participles")),
                forms=_verb_forms_from_payload(payload.get("forms")),
            )
            DATABASE.save_word_base(word_id, lemma=save.lemma, english=save.english)
            DATABASE.save_verb_participles(word_id, save.participles)
            DATABASE.save_verb_forms(word_id, save.forms)
        else:
            raise ApiError(f"unsupported word type: {word_type}")
        self._send_json({"ok": True, "word": DATABASE.load_word(word_id)})

    def _api_delete_word(self, word_id: int) -> None:
        if not DATABASE.delete_word(word_id):
            raise ApiError("word not found", HTTPStatus.NOT_FOUND)
        self._send_json({"ok": True})

    def _read_json(self) -> dict[str, object]:
        length_text = self.headers.get("Content-Length") or "0"
        try:
            length = int(length_text)
        except ValueError as exc:
            raise ApiError("invalid Content-Length") from exc
        if length > 3_000_000:
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


def _one(query: dict[str, list[str]], key: str, *, default: str | None = None) -> str:
    values = query.get(key)
    if not values:
        if default is not None:
            return default
        raise ApiError(f"missing query parameter: {key}")
    return values[0]


def _required_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if value is None:
        raise ApiError(f"missing field: {key}")
    if not isinstance(value, str):
        raise ApiError(f"field must be a string: {key}")
    return value


def _word_id_from_path(path: str) -> int | None:
    prefix = "/api/words/"
    if not path.startswith(prefix):
        return None
    raw = path[len(prefix):].strip("/")
    if not raw or "/" in raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _nominal_forms_from_payload(raw: object) -> dict[tuple[str, str], str | None]:
    forms = empty_nominal_forms()
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
    return forms


def _participles_from_payload(raw: object) -> dict[str, dict[str, object]]:
    result = {value: {"form": None, "is_irregular": False} for value in PARTICIPLE_TYPES}
    if raw is None:
        return result
    if not isinstance(raw, dict):
        raise ApiError("participles must be an object")
    for participle_type in PARTICIPLE_TYPES:
        result[participle_type] = _irregular_payload(raw.get(participle_type), f"participles.{participle_type}")
    return result


def _verb_forms_from_payload(raw: object) -> dict[tuple[str, str], dict[str, object]]:
    result: dict[tuple[str, str], dict[str, object]] = {}
    if raw is None:
        return result
    if not isinstance(raw, dict):
        raise ApiError("forms must be an object")
    for tense_code, person_map in raw.items():
        if not isinstance(tense_code, str):
            raise ApiError("verb form tense keys must be strings")
        if not isinstance(person_map, dict):
            raise ApiError(f"forms.{tense_code} must be an object")
        for person_code, payload in person_map.items():
            if not isinstance(person_code, str):
                raise ApiError(f"forms.{tense_code} person keys must be strings")
            result[(tense_code, person_code)] = _irregular_payload(payload, f"forms.{tense_code}.{person_code}")
    return result


def _irregular_payload(raw: object, path: str) -> dict[str, object]:
    if raw is None:
        return {"form": None, "is_irregular": False}
    if not isinstance(raw, dict):
        raise ApiError(f"{path} must be an object")
    form = raw.get("form")
    if form is not None and not isinstance(form, str):
        raise ApiError(f"{path}.form must be a string or null")
    return {"form": form, "is_irregular": bool(raw.get("is_irregular", False))}


def main() -> int:
    host = os.environ.get("SPANISH_FLASHCARDS_HOST", "127.0.0.1")
    port = int(os.environ.get("SPANISH_FLASHCARDS_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), FlashcardsHandler)
    print(f"Spanish Flashcards web app: http://{host}:{port}")
    print(f"Database: {DB_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
