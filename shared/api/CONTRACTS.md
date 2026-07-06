# API contracts

Localhost-only Spanish Word Bank app. Binds to `127.0.0.1` by default. No authentication.

## Envelope

All JSON API responses use:

- **Success:** `{ "ok": true, ...payload }`
- **Error:** `{ "ok": false, "error": "<message>" }` with HTTP 400/404/405/413/500

Request bodies must be JSON objects unless noted.

---

## Word Bank (`word_bank/gui.py`, port 8000)

| Method | Path | Request | Response |
|--------|------|---------|----------|
| GET | `/api/meta` | — | Meta catalog (types, genders, numbers, verb meta, `lexical_item_type_labels`) |
| GET | `/api/search?lexical_item_type=&q=` | Query params | `{ ok, results[] }` — matches `headword` and `explanation` (headword matches ranked first) |
| GET | `/api/lexical-items/{id}` | — | `{ ok, lexical_item }` |
| POST | `/api/lexical-items` | Lexical item save body | `{ ok, lexical_item }` (201) |
| PUT | `/api/lexical-items/{id}` | Lexical item save body | `{ ok, lexical_item }` |
| DELETE | `/api/lexical-items/{id}` | — | `{ ok }` |

### Lexical item save (`parse_lexical_item_save`)

Common fields: `headword`, `explanation`, `lexical_item_type`.

| Type | Extra fields | Forms shape |
|------|--------------|-------------|
| noun | `gender_availability` | `{ singular: { masculine, feminine }, plural: { ... } }` |
| adjective | `adjective_inflection_type` | `{ singular/plural: { masculine, feminine, shared } }` |
| other | `inflection_type` | Same nested number/gender/shared object |
| verb | — | `{ <verb_form_code>: { form: string\|null } }` |

Parsed into `NounSavePayload`, `AdjectiveSavePayload`, `OtherSavePayload`, or `VerbSavePayload` in `shared/api/word_bank_requests.py`.
