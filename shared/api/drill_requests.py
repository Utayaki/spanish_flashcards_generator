from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.api.envelope import optional_int, require_int, require_object, require_str
from shared.http.errors import ApiError

VALID_RATINGS = frozenset({"again", "hard", "good", "easy"})
VALID_SESSION_MODES = frozenset({"random", "review"})
VALID_DRILL_TYPES = frozenset({"inflection", "verb_form", "recognition", "reverse", "transform"})


@dataclass(frozen=True)
class CheckRequest:
    drill_card_id: int
    session_id: int | None
    response_ms: int | None
    answers: dict[str, Any]

    @classmethod
    def from_json(cls, body: object) -> CheckRequest:
        payload = require_object(body)
        answers = payload.get("answers")
        if not isinstance(answers, dict):
            raise ApiError("answers required")
        normalized_answers: dict[str, Any] = {}
        for key, value in answers.items():
            if not isinstance(key, str):
                raise ApiError("answer keys must be strings")
            normalized_answers[key] = value
        return cls(
            drill_card_id=require_int(payload, "drill_card_id"),
            session_id=optional_int(payload, "session_id"),
            response_ms=optional_int(payload, "response_ms"),
            answers=normalized_answers,
        )


@dataclass(frozen=True)
class RateRequest:
    drill_card_id: int
    attempt_id: int | None
    rating: str
    review_duration_ms: int | None

    @classmethod
    def from_json(cls, body: object) -> RateRequest:
        payload = require_object(body)
        rating = require_str(payload, "rating")
        if rating not in VALID_RATINGS:
            raise ApiError("rating must be one of: again, hard, good, easy")
        return cls(
            drill_card_id=require_int(payload, "drill_card_id"),
            attempt_id=optional_int(payload, "attempt_id"),
            rating=rating,
            review_duration_ms=optional_int(payload, "review_duration_ms"),
        )


@dataclass(frozen=True)
class CreateSessionRequest:
    mode: str
    drill_type: str | None

    @classmethod
    def from_json(cls, body: object) -> CreateSessionRequest:
        payload = require_object(body)
        mode = str(payload.get("mode", "random"))
        if mode not in VALID_SESSION_MODES:
            raise ApiError("mode must be one of: random, review")
        drill_type_raw = payload.get("drill_type")
        drill_type: str | None = None
        if drill_type_raw is not None:
            drill_type = str(drill_type_raw)
            if drill_type not in VALID_DRILL_TYPES:
                raise ApiError(f"invalid drill type: {drill_type}")
        return cls(mode=mode, drill_type=drill_type)


def parse_check_request(body: object) -> CheckRequest:
    return CheckRequest.from_json(body)


def parse_rate_request(body: object) -> RateRequest:
    return RateRequest.from_json(body)


def parse_create_session_request(body: object) -> CreateSessionRequest:
    return CreateSessionRequest.from_json(body)
