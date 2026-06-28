from __future__ import annotations

from typing import Any

PERSONS = (
    ("yo", "yo"),
    ("tu", "tú"),
    ("vos", "vos"),
    ("el_ella_usted", "él/ella/Ud."),
    ("nosotros_nosotras", "nosotros/nosotras"),
    ("vosotros_vosotras", "vosotros/vosotras"),
    ("ellos_ellas_ustedes", "ellos/ellas/Uds."),
)

IMPERATIVE_PERSONS = (
    ("tu", "tú"),
    ("vos", "vos"),
    ("el_ella_usted", "Ud."),
    ("nosotros_nosotras", "nosotros/nosotras"),
    ("vosotros_vosotras", "vosotros/vosotras"),
    ("ellos_ellas_ustedes", "Uds."),
)

VERB_GROUPS = (
    ("participle", "Participles"),
    ("indicative", "Indicative"),
    ("subjunctive", "Subjunctive"),
    ("imperative", "Imperative"),
    ("progressive", "Progressive"),
    ("perfect", "Perfect"),
    ("perfect_subjunctive", "Perfect Subj."),
    ("informal_future", "Informal Future"),
)

PARTICIPLES = (
    ("present", "Present"),
    ("past", "Past"),
)

INDICATIVE_TENSES = (
    ("present", "Present"),
    ("preterite", "Preterite"),
    ("imperfect", "Imperfect"),
    ("conditional", "Conditional"),
    ("future", "Future"),
)

SUBJUNCTIVE_TENSES = (
    ("present", "Present", None),
    ("imperfect", "Imperfect -ra", "ra"),
    ("imperfect", "Imperfect -se", "se"),
    ("future", "Future", None),
)

IMPERATIVE_TENSES = (
    ("affirmative", "Affirmative"),
    ("negative", "Negative"),
)

PERFECT_SUBJUNCTIVE_TENSES = (
    ("present", "Present", None),
    ("past", "Past -ra", "ra"),
    ("past", "Past -se", "se"),
    ("future", "Future", None),
)

GROUP_LABELS = dict(VERB_GROUPS)
VERB_FORM_COUNT = 182


def build_verb_form_definitions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    next_id = 1

    def add(
        *,
        code: str,
        group_code: str,
        tense_code: str | None = None,
        tense_label: str | None = None,
        person_code: str | None = None,
        person_label: str | None = None,
    ) -> None:
        nonlocal next_id
        rows.append(
            {
                "id": next_id,
                "code": code,
                "group_code": group_code,
                "group_label": GROUP_LABELS[group_code],
                "tense_code": tense_code,
                "tense_label": tense_label,
                "person_code": person_code,
                "person_label": person_label,
                "sort_order": next_id,
            }
        )
        next_id += 1

    for participle_code, participle_label in PARTICIPLES:
        add(
            code=f"participle_{participle_code}",
            group_code="participle",
            tense_code=participle_code,
            tense_label=participle_label,
        )

    add_person_tenses(add, "indicative", INDICATIVE_TENSES, PERSONS)
    add_variant_tenses(add, "subjunctive", SUBJUNCTIVE_TENSES, PERSONS)
    add_person_tenses(add, "imperative", IMPERATIVE_TENSES, IMPERATIVE_PERSONS)
    add_person_tenses(add, "progressive", INDICATIVE_TENSES, PERSONS)
    add_person_tenses(add, "perfect", INDICATIVE_TENSES, PERSONS)
    add_variant_tenses(add, "perfect_subjunctive", PERFECT_SUBJUNCTIVE_TENSES, PERSONS)

    for person_code, person_label in PERSONS:
        add(
            code=f"informal_future_{person_code}",
            group_code="informal_future",
            tense_code="future",
            tense_label="Informal Future",
            person_code=person_code,
            person_label=person_label,
        )

    if len(rows) != VERB_FORM_COUNT:
        raise RuntimeError(f"expected {VERB_FORM_COUNT} verb forms, built {len(rows)}")
    return rows


def add_person_tenses(add: Any, group_code: str, tenses: tuple[tuple[str, str], ...], persons: tuple[tuple[str, str], ...]) -> None:
    for tense_code, tense_label in tenses:
        for person_code, person_label in persons:
            add(
                code=f"{group_code}_{tense_code}_{person_code}",
                group_code=group_code,
                tense_code=tense_code,
                tense_label=tense_label,
                person_code=person_code,
                person_label=person_label,
            )


def add_variant_tenses(
    add: Any,
    group_code: str,
    tenses: tuple[tuple[str, str, str | None], ...],
    persons: tuple[tuple[str, str], ...],
) -> None:
    for tense_code, tense_label, variant_code in tenses:
        merged_tense_code = f"{tense_code}_{variant_code}" if variant_code else tense_code
        for person_code, person_label in persons:
            add(
                code="_".join([group_code, merged_tense_code, person_code]),
                group_code=group_code,
                tense_code=merged_tense_code,
                tense_label=tense_label,
                person_code=person_code,
                person_label=person_label,
            )


def build_verb_meta(definitions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    source = VERB_FORM_DEFINITIONS if definitions is None else definitions
    ordered = sorted(source, key=lambda row: int(row["sort_order"]))
    participles: list[dict[str, Any]] = []
    groups: dict[str, dict[str, Any]] = {}

    for row in ordered:
        group_code = str(row["group_code"])
        if group_code == "participle":
            participles.append(_form_meta(row))
            continue

        group = groups.setdefault(
            group_code,
            {
                "code": group_code,
                "label": row["group_label"],
                "tenses": [],
                "persons": [],
            },
        )
        tense_code = _ui_tense_code(row)
        tense = next((item for item in group["tenses"] if item["code"] == tense_code), None)
        if tense is None:
            tense = {
                "code": tense_code,
                "label": row["tense_label"],
                "forms": [],
            }
            group["tenses"].append(tense)
        tense["forms"].append(_form_meta(row))

        person = {"code": row["person_code"], "label": row["person_label"]}
        if person not in group["persons"]:
            group["persons"].append(person)

    return {
        "verb_form_count": len(ordered),
        "verb_participles": participles,
        "verb_groups": [groups[code] for code, _ in VERB_GROUPS if code in groups],
    }


def _ui_tense_code(row: dict[str, Any]) -> str:
    return str(row["tense_code"])


def _form_meta(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "code": row["code"],
        "label": row["tense_label"],
        "group_code": row["group_code"],
        "tense_code": row["tense_code"],
        "tense_label": row["tense_label"],
        "person_code": row["person_code"],
        "person_label": row["person_label"],
    }


PERSISTED_VERB_FORM_COLUMNS = ("id", "group_code", "tense_code", "person_code", "sort_order")


def persisted_verb_form_rows() -> list[dict[str, Any]]:
    return [
        {column: row[column] for column in PERSISTED_VERB_FORM_COLUMNS}
        for row in VERB_FORM_DEFINITIONS
    ]


VERB_FORM_DEFINITIONS = build_verb_form_definitions()
VERB_FORM_CODES = {str(row["code"]) for row in VERB_FORM_DEFINITIONS}
VERB_FORM_CODE_BY_ID = {int(row["id"]): str(row["code"]) for row in VERB_FORM_DEFINITIONS}
VERB_FORM_ID_BY_CODE = {str(row["code"]): int(row["id"]) for row in VERB_FORM_DEFINITIONS}
