from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from widgets.form_state import normalize_optional_form

VERB_GROUP_ORDER = (
    "indicative",
    "subjunctive",
    "imperative",
    "progressive",
    "perfect",
    "perfect_subjunctive",
    "informal_future",
)

VERB_GROUP_LABELS = {
    "indicative": "Indicative",
    "subjunctive": "Subjunctive",
    "imperative": "Imperative",
    "progressive": "Progressive",
    "perfect": "Perfect",
    "perfect_subjunctive": "Perfect Subj.",
    "informal_future": "Informal Future",
}

EXPECTED_TENSE_CODES_BY_GROUP = {
    "indicative": (
        "indicative_present",
        "indicative_preterite",
        "indicative_imperfect",
        "indicative_conditional",
        "indicative_future",
    ),
    "subjunctive": (
        "subjunctive_present",
        "subjunctive_imperfect",
        "subjunctive_future",
    ),
    "imperative": (
        "imperative_affirmative",
        "imperative_negative",
    ),
    "progressive": (
        "progressive_present",
        "progressive_preterite",
        "progressive_imperfect",
        "progressive_conditional",
        "progressive_future",
    ),
    "perfect": (
        "perfect_present",
        "perfect_preterite",
        "perfect_past",
        "perfect_conditional",
        "perfect_future",
    ),
    "perfect_subjunctive": (
        "perfect_subjunctive_present",
        "perfect_subjunctive_past",
        "perfect_subjunctive_future",
    ),
    "informal_future": ("informal_future",),
}

PARTICIPLE_TYPES = ("present", "past")
PARTICIPLE_LABELS = {
    "present": "Present",
    "past": "Past",
}

PERSON_CODES = (
    "yo",
    "tu",
    "vos",
    "el_ella_usted",
    "nosotros",
    "vosotros",
    "ellos_ellas_ustedes",
)

PERSON_LABELS = {
    "yo": "yo",
    "tu": "tú",
    "vos": "vos",
    "el_ella_usted": "él/ella/Ud.",
    "nosotros": "nosotros",
    "vosotros": "vosotros",
    "ellos_ellas_ustedes": "ellos/ellas/Uds.",
}

IMPERATIVE_PERSON_LABELS = {
    "yo": "yo",
    "tu": "tú",
    "vos": "vos",
    "el_ella_usted": "Ud.",
    "nosotros": "nosotros",
    "vosotros": "vosotros",
    "ellos_ellas_ustedes": "Uds.",
}

EXPECTED_FORM_COUNT = sum(len(codes) for codes in EXPECTED_TENSE_CODES_BY_GROUP.values()) * len(PERSON_CODES)


class VerbEditorStateError(ValueError):
    """Raised when verb-editor state is invalid."""


def ensure_verb_word_type(word_type: str) -> str:
    if word_type != "verb":
        raise VerbEditorStateError(f"expected verb word type, got: {word_type}")
    return word_type


def editor_title(lemma: str) -> str:
    clean_lemma = lemma.strip() or "Untitled"
    return f"Verb: {clean_lemma}"


def normalize_form_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {"form": normalize_optional_form(payload.get("form"))}


def group_tenses(tenses: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group DB tense rows in the exact UI order used by the verb tabs."""

    grouped: dict[str, list[dict[str, Any]]] = {group: [] for group in VERB_GROUP_ORDER}
    for tense in sorted(tenses, key=lambda row: int(row["sort_order"])):
        group = str(tense["group_code"])
        if group not in grouped:
            raise VerbEditorStateError(f"unexpected verb tense group: {group}")
        grouped[group].append(dict(tense))

    for group, expected_codes in EXPECTED_TENSE_CODES_BY_GROUP.items():
        found_codes = tuple(str(tense["code"]) for tense in grouped[group])
        if found_codes != expected_codes:
            raise VerbEditorStateError(
                f"verb tense seed mismatch for {group}: expected {expected_codes}, got {found_codes}"
            )

    return grouped


def ordered_persons(persons: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = [dict(person) for person in sorted(persons, key=lambda row: int(row["sort_order"]))]
    found_codes = tuple(str(person["code"]) for person in ordered)
    if found_codes != PERSON_CODES:
        raise VerbEditorStateError(f"verb person seed mismatch: expected {PERSON_CODES}, got {found_codes}")
    return ordered


def person_label_for_group(person: dict[str, Any], group_code: str) -> str:
    if group_code == "imperative":
        return str(person.get("imperative_label") or IMPERATIVE_PERSON_LABELS[str(person["code"])])
    return str(person.get("label") or PERSON_LABELS[str(person["code"])])


def empty_participles() -> dict[str, dict[str, Any]]:
    return {participle_type: {"form": None} for participle_type in PARTICIPLE_TYPES}


def empty_verb_forms() -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (tense_code, person_code): {"form": None}
        for tense_codes in EXPECTED_TENSE_CODES_BY_GROUP.values()
        for tense_code in tense_codes
        for person_code in PERSON_CODES
    }


def extract_forms_from_loaded_verb(loaded_verb: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    forms = empty_verb_forms()
    loaded_groups = loaded_verb.get("forms", {})

    for group_data in loaded_groups.values():
        for tense_code, tense_data in group_data.items():
            for person_code, person_data in tense_data.get("persons", {}).items():
                key = (str(tense_code), str(person_code))
                if key in forms:
                    forms[key] = normalize_form_payload({"form": person_data.get("form")})
    return forms


def extract_participles_from_loaded_verb(loaded_verb: dict[str, Any]) -> dict[str, dict[str, Any]]:
    participles = empty_participles()
    loaded_participles = loaded_verb.get("participles", {})

    for participle_type in PARTICIPLE_TYPES:
        payload = loaded_participles.get(participle_type, {})
        participles[participle_type] = normalize_form_payload({"form": payload.get("form")})
    return participles


@dataclass(frozen=True)
class VerbSavePayload:
    lemma: str
    english: str
    participles: dict[str, dict[str, Any]]
    forms: dict[tuple[str, str], dict[str, Any]]

    @classmethod
    def from_inputs(
        cls,
        *,
        lemma: str,
        english: str,
        participles: dict[str, dict[str, Any]],
        forms: dict[tuple[str, str], dict[str, Any]],
    ) -> "VerbSavePayload":
        clean_lemma = lemma.strip()
        if not clean_lemma:
            raise VerbEditorStateError("lemma cannot be empty")

        clean_participles = empty_participles()
        for participle_type, payload in participles.items():
            if participle_type not in PARTICIPLE_TYPES:
                raise VerbEditorStateError(f"invalid participle type: {participle_type}")
            clean_participles[participle_type] = normalize_form_payload(payload)

        clean_forms = empty_verb_forms()
        for key, payload in forms.items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise VerbEditorStateError(f"invalid verb form key: {key!r}")
            tense_code, person_code = key
            if tense_code not in {code for codes in EXPECTED_TENSE_CODES_BY_GROUP.values() for code in codes}:
                raise VerbEditorStateError(f"invalid tense code: {tense_code}")
            if person_code not in PERSON_CODES:
                raise VerbEditorStateError(f"invalid person code: {person_code}")
            clean_forms[(tense_code, person_code)] = normalize_form_payload(payload)

        clean_english = english.strip()
        if not clean_english:
            raise VerbEditorStateError("english definition cannot be empty")

        return cls(
            lemma=clean_lemma,
            english=clean_english,
            participles=clean_participles,
            forms=clean_forms,
        )

    def as_debug_dict(self) -> dict[str, Any]:
        return {
            "lemma": self.lemma,
            "english": self.english,
            "participles": self.participles,
            "form_count": len(self.forms),
        }
