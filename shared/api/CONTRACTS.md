# API contracts

Localhost-only Spanish Word Bank and Drill apps. Both bind to `127.0.0.1` by default. No authentication.

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
| GET | `/api/search?lexical_item_type=&q=` | Query params | `{ ok, results[] }` |
| GET | `/api/lexical-items/{id}` | — | `{ ok, lexical_item }` |
| POST | `/api/lexical-items` | Lexical item save body | `{ ok, lexical_item, sync_warning? }` (201) |
| PUT | `/api/lexical-items/{id}` | Lexical item save body | `{ ok, lexical_item, sync_warning? }` |
| DELETE | `/api/lexical-items/{id}` | — | `{ ok, sync_warning? }` |

### Lexical item save (`parse_lexical_item_save`)

Common fields: `headword`, `explanation`, `lexical_item_type`.

| Type | Extra fields | Forms shape |
|------|--------------|-------------|
| noun | `gender_availability` | `{ singular: { masculine, feminine }, plural: { ... } }` |
| adjective | `adjective_inflection_type` | `{ singular/plural: { masculine, feminine, shared } }` |
| other | `inflection_type` | Same nested number/gender/shared object |
| verb | — | `{ <verb_form_code>: { form: string\|null } }` |

Parsed into `NounSavePayload`, `AdjectiveSavePayload`, `OtherSavePayload`, or `VerbSavePayload` in `shared/api/word_bank_requests.py`.

---

## Drill (`drill/gui.py`, port 8001)

| Method | Path | Request dataclass | Response |
|--------|------|-------------------|----------|
| GET | `/api/meta` | — | Drill types, numbers, genders, verb meta, **`answer_schemas`** |
| GET | `/api/drill/stats` | — | `{ ok, stats, schedule }` |
| GET | `/api/drill/due-count` | — | `{ ok, due_review_count, new_card_count, due_by_type }` |
| GET | `/api/drill/review/next?type=` | — | `{ ok, done, question?, review_mode?, due counts }` |
| GET | `/api/drill/random?type=` | — | `{ ok, question }` |
| POST | `/api/drill/check` | `CheckRequest` | `{ ok, attempt_id, correct, results, reveal, expected_answer, submitted_answer }` |
| POST | `/api/drill/review/rate` | `RateRequest` | `{ ok, review_log_id, rating, next_due_at, ...due counts }` |
| POST | `/api/drill/sessions` | `CreateSessionRequest` | `{ ok, session_id }` |
| POST | `/api/drill/sessions/{id}/finish` | — | `{ ok }` |

### `CheckRequest` (`shared/api/drill_requests.py`)

```json
{
  "drill_card_id": 1,
  "session_id": 2,
  "response_ms": 5000,
  "answers": { "user_*": "..." }
}
```

### `RateRequest`

```json
{
  "drill_card_id": 1,
  "attempt_id": 99,
  "rating": "again|hard|good|easy",
  "review_duration_ms": 3000
}
```

### `CreateSessionRequest`

```json
{
  "mode": "random|review",
  "drill_type": "inflection|null"
}
```

---

## Drill answer keys (`shared/api/drill_answers.py`)

Canonical `user_*` fields per drill type. The server validates exact key sets on check (no missing or extra keys).

| drill_type | Answer keys |
|------------|-------------|
| inflection | `user_inflection_pattern`, `user_form` |
| verb_form | `user_form` |
| transform | `user_form` |
| reverse | `user_headword`, `user_form` |
| recognition (number_gender) | `user_translation`, `user_number`, `user_gender` |
| recognition (verb) | `user_translation`, `user_group_code`, `user_tense_code`, `user_person_code` |
| recognition (verb participle) | `user_translation`, `user_group_code`, `user_tense_code` |

Recognition variant selection uses question fields (`metadata_kind`, `group_code`). The frontend reads the same contract from `/api/meta` → `answer_schemas`.

Default for participle group: `answer_schemas.defaults.participle_group_code` = `"participle"`.

Grading is server-authoritative: check rebuilds the question from `drill_card_id` and loads expected answers from the database.
