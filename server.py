from __future__ import annotations

import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from controllers.adjective_editor_state import AdjectiveSavePayload
from controllers.noun_editor_state import GENDER_CHOICES, NounSavePayload
from controllers.other_editor_state import OtherSavePayload
from controllers.start_page_presenter import LEMMA_CLASS_META, validate_lemma_type
from controllers.verb_editor_state import (
    PARTICIPLE_LABELS,
    PARTICIPLE_TYPES,
    VERB_GROUP_LABELS,
    VerbSavePayload,
    group_tenses,
    ordered_persons,
)
from database import DatabaseError, SpanishLemmaDatabase, ValidationError
from widgets.form_state import GENDERS, NUMBERS, SHARED_GENDER_KEY, empty_gendered_forms, empty_shared_forms

APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
STATIC_DIR = WEB_DIR / "static"
DEFAULT_DB_PATH = APP_DIR / "spanish_words.db"
DB_PATH = Path(os.environ.get("SPANISH_FLASHCARDS_DB", DEFAULT_DB_PATH))

DATABASE = SpanishLemmaDatabase(DB_PATH)


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
        except Exception as exc:
            self._send_json({"ok": False, "error": f"unexpected server error: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_api(self, method: str, path: str, query: dict[str, list[str]]) -> None:
        if method == "GET" and path == "/api/meta":
            self._api_meta()
            return
        if method == "GET" and path == "/api/search":
            self._api_search(query)
            return
        if method == "POST" and path == "/api/lemmas":
            self._api_create_lemma()
            return
        lemma_id = _lemma_id_from_path(path)
        if lemma_id is None:
            raise ApiError("not found", HTTPStatus.NOT_FOUND)
        if method == "GET":
            self._api_get_lemma(lemma_id)
        elif method == "PUT":
            self._api_update_lemma(lemma_id)
        elif method == "DELETE":
            self._api_delete_lemma(lemma_id)
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
                "lemma_types": LEMMA_CLASS_META,
                "gender_choices": [{"value": value, "label": label} for value, label in GENDER_CHOICES],
                "numbers": list(NUMBERS),
                "genders": list(GENDERS),
                "shared_gender_key": SHARED_GENDER_KEY,
                "participle_types": [
                    {"value": value, "label": PARTICIPLE_LABELS[value]} for value in PARTICIPLE_TYPES
                ],
                "verb_groups": verb_groups,
                "persons": persons,
                "other_inflection_types": [
                    {"value": "none", "label": "No inflections"},
                    {"value": "plurality", "label": "Plurality"},
                    {"value": "gender_plurality", "label": "Plurality + gender"},
                ],
                "adjective_inflection_types": [
                    {"value": "plurality", "label": "Plurality"},
                    {"value": "gender_plurality", "label": "Plurality + gender"},
                ],
            }
        )

    def _api_search(self, query: dict[str, list[str]]) -> None:
        lemma_type = _one(query, "lemma_type")
        lemma = _one(query, "q", default="")
        validate_lemma_type(lemma_type)
        results = DATABASE.search_lemmas(lemma_type, lemma, limit=10)
        self._send_json({"ok": True, "results": results})

    def _api_get_lemma(self, lemma_id: int) -> None:
        self._send_json({"ok": True, "lemma": DATABASE.load_lemma(lemma_id)})

    def _api_create_lemma(self) -> None:
        payload = self._read_json()
        lemma_type = validate_lemma_type(_required_str(payload, "lemma_type"))

        if lemma_type == "noun":
            save = NounSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                gender_availability=_required_str(payload, "gender_availability"),
                forms=_forms_from_payload(payload.get("forms"), include_shared=False),
            )
            lemma_id = DATABASE.create_noun_lemma(
                lemma=save.lemma,
                english=save.english,
                gender_availability=save.gender_availability,
                forms=save.forms,
            )
        elif lemma_type == "adjective":
            save = AdjectiveSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                inflection_type=_adjective_type_from_payload(payload),
                forms=_forms_from_payload(payload.get("forms"), include_shared=True),
            )
            lemma_id = DATABASE.create_adjective_lemma(
                lemma=save.lemma,
                english=save.english,
                inflection_type=save.inflection_type,
                forms=save.forms,
            )
        elif lemma_type == "other":
            save = OtherSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                inflection_type=_required_str(payload, "inflection_type"),
                forms=_forms_from_payload(payload.get("forms"), include_shared=True),
            )
            lemma_id = DATABASE.create_other_lemma(
                lemma=save.lemma,
                english=save.english,
                inflection_type=save.inflection_type,
                forms=save.forms,
            )
        else:
            save = VerbSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                participles=_participles_from_payload(payload.get("participles")),
                forms=_verb_forms_from_payload(payload.get("forms")),
            )
            lemma_id = DATABASE.create_verb_lemma(
                lemma=save.lemma,
                english=save.english,
                participles=save.participles,
                forms=save.forms,
            )
        self._send_json({"ok": True, "lemma": DATABASE.load_lemma(lemma_id)}, HTTPStatus.CREATED)

    def _api_update_lemma(self, lemma_id: int) -> None:
        existing = DATABASE.get_lemma_summary(lemma_id)
        if existing is None:
            raise ApiError("lemma not found", HTTPStatus.NOT_FOUND)
        payload = self._read_json()
        lemma_type = str(existing["lemma_type"])
        submitted_type = payload.get("lemma_type")
        if submitted_type is not None and submitted_type != lemma_type:
            raise ApiError("changing lemma type is not supported")

        if lemma_type == "noun":
            save = NounSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                gender_availability=_required_str(payload, "gender_availability"),
                forms=_forms_from_payload(payload.get("forms"), include_shared=False),
            )
            DATABASE.save_lemma_base(lemma_id, lemma=save.lemma, english=save.english)
            DATABASE.save_noun_details(lemma_id, save.gender_availability)
            DATABASE.save_noun_forms(lemma_id, save.forms)
        elif lemma_type == "adjective":
            save = AdjectiveSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                inflection_type=_adjective_type_from_payload(payload),
                forms=_forms_from_payload(payload.get("forms"), include_shared=True),
            )
            DATABASE.save_lemma_base(lemma_id, lemma=save.lemma, english=save.english)
            DATABASE.save_adjective_details(lemma_id, save.inflection_type)
            DATABASE.save_adjective_forms(lemma_id, save.forms)
        elif lemma_type == "other":
            save = OtherSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                inflection_type=_required_str(payload, "inflection_type"),
                forms=_forms_from_payload(payload.get("forms"), include_shared=True),
            )
            DATABASE.save_lemma_base(lemma_id, lemma=save.lemma, english=save.english)
            DATABASE.save_other_details(lemma_id, save.inflection_type)
            DATABASE.save_other_inflections(lemma_id, save.forms)
        elif lemma_type == "verb":
            save = VerbSavePayload.from_inputs(
                lemma=_required_str(payload, "lemma"),
                english=_required_str(payload, "english"),
                participles=_participles_from_payload(payload.get("participles")),
                forms=_verb_forms_from_payload(payload.get("forms")),
            )
            DATABASE.save_lemma_base(lemma_id, lemma=save.lemma, english=save.english)
            DATABASE.save_verb_participles(lemma_id, save.participles)
            DATABASE.save_verb_forms(lemma_id, save.forms)
        else:
            raise ApiError(f"unsupported lemma type: {lemma_type}")
        self._send_json({"ok": True, "lemma": DATABASE.load_lemma(lemma_id)})

    def _api_delete_lemma(self, lemma_id: int) -> None:
        if not DATABASE.delete_lemma(lemma_id):
            raise ApiError("lemma not found", HTTPStatus.NOT_FOUND)
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


def _adjective_type_from_payload(payload: dict[str, object]) -> str:
    value = payload.get("adjective_inflection_type", "gender_plurality")
    if not isinstance(value, str):
        raise ApiError("adjective_inflection_type must be a string")
    if value not in {"plurality", "gender_plurality"}:
        raise ApiError(f"invalid adjective_inflection_type: {value}")
    return value


def _lemma_id_from_path(path: str) -> int | None:
    prefix = "/api/lemmas/"
    if not path.startswith(prefix):
        return None
    raw = path[len(prefix):].strip("/")
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


def _participles_from_payload(raw: object) -> dict[str, dict[str, object]]:
    result = {value: {"form": None} for value in PARTICIPLE_TYPES}
    if raw is None:
        return result
    if not isinstance(raw, dict):
        raise ApiError("participles must be an object")
    for participle_type in PARTICIPLE_TYPES:
        result[participle_type] = _form_payload(raw.get(participle_type), f"participles.{participle_type}")
    return result


def _verb_forms_from_payload(raw: object) -> dict[tuple[str, str], dict[str, object]]:
    result: dict[tuple[str, str], dict[str, object]] = {}
    if raw is None:
        return result
    if not isinstance(raw, dict):
        raise ApiError("forms must be an object")
    for tense_code, person_map in raw.items():
        if not isinstance(tense_code, str):
            raise ApiError("verb tense keys must be strings")
        if not isinstance(person_map, dict):
            raise ApiError(f"forms.{tense_code} must be an object")
        for person_code, payload in person_map.items():
            if not isinstance(person_code, str):
                raise ApiError(f"forms.{tense_code} person keys must be strings")
            result[(tense_code, person_code)] = _form_payload(payload, f"forms.{tense_code}.{person_code}")
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
    server = ThreadingHTTPServer((host, port), FlashcardsHandler)
    print(f"Serving Spanish Lemma DB at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
