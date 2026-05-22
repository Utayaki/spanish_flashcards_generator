from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
import re
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from controllers.verb_editor_state import (
    EXPECTED_TENSE_CODES_BY_GROUP,
    PARTICIPLE_TYPES,
    PERSON_CODES,
    empty_participles,
    empty_verb_forms,
    normalize_irregular_payload,
)

SPANISHDICT_CONJUGATE_URL = "https://www.spanishdict.com/conjugate/{lemma}"
JINA_READER_PREFIX = "https://r.jina.ai/"
DEFAULT_TIMEOUT_SECONDS = 20

_BROWSER_HEADERS = {
    # Do not identify as a bot. SpanishDict can return 403 to basic Python/urllib requests.
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,es;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.spanishdict.com/conjugate/",
}

_READER_HEADERS = {
    "User-Agent": _BROWSER_HEADERS["User-Agent"],
    "Accept": "text/plain,text/markdown,*/*;q=0.8",
    "Accept-Language": _BROWSER_HEADERS["Accept-Language"],
}


@dataclass(frozen=True)
class ImportedForm:
    """One imported form preview.

    `form=None` means the source page showed no usable form, usually `-`.
    `is_irregular` is best-effort because SpanishDict marks irregular pieces in
    presentation markup that can change over time.
    """

    form: str | None
    is_irregular: bool = False

    def as_payload(self) -> dict[str, object]:
        return normalize_irregular_payload(
            {"form": self.form, "is_irregular": self.is_irregular}
        )


@dataclass(frozen=True)
class ImportedVerb:
    lemma: str
    participles: dict[str, ImportedForm]
    forms: dict[tuple[str, str], ImportedForm]
    warnings: list[str] = field(default_factory=list)

    @property
    def non_empty_participle_count(self) -> int:
        return sum(1 for form in self.participles.values() if form.form is not None)

    @property
    def non_empty_form_count(self) -> int:
        return sum(1 for form in self.forms.values() if form.form is not None)

    @property
    def irregular_count(self) -> int:
        return sum(1 for form in self.participles.values() if form.is_irregular) + sum(
            1 for form in self.forms.values() if form.is_irregular
        )

    def participles_payload(self) -> dict[str, dict[str, object]]:
        payload = empty_participles()
        for participle_type, imported in self.participles.items():
            if participle_type in payload:
                payload[participle_type] = imported.as_payload()
        return payload

    def forms_payload(self) -> dict[tuple[str, str], dict[str, object]]:
        payload = empty_verb_forms()
        for key, imported in self.forms.items():
            if key in payload:
                payload[key] = imported.as_payload()
        return payload


class SpanishDictImportError(RuntimeError):
    """Raised when SpanishDict import cannot produce a safe preview."""


@dataclass(frozen=True)
class _TextItem:
    text: str
    is_form_link: bool = False
    is_irregular: bool = False


class _VisibleTextParser(HTMLParser):
    """Small HTML-to-text parser tuned for SpanishDict conjugation pages.

    It intentionally avoids any third-party parser dependency. The output is a
    flat stream of visible text items, with anchor text kept as one unit because
    SpanishDict usually places conjugated forms inside links.
    """

    _IGNORED_TAGS = {"script", "style", "noscript", "svg"}
    _BLOCK_TAGS = {
        "br",
        "p",
        "div",
        "section",
        "article",
        "header",
        "footer",
        "main",
        "table",
        "thead",
        "tbody",
        "tr",
        "td",
        "th",
        "ul",
        "ol",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[_TextItem] = []
        self._ignore_depth = 0
        self._link_depth = 0
        self._link_chunks: list[str] = []
        self._link_irregular_stack: list[bool] = []
        self._text_chunks: list[str] = []
        self._irregular_context_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self._IGNORED_TAGS:
            self._ignore_depth += 1
            return
        if self._ignore_depth:
            return

        if tag == "a":
            self._flush_text_chunks()
            self._link_depth += 1
            self._link_chunks = []
            self._link_irregular_stack = []

        if self._looks_irregular(tag, attrs):
            self._irregular_context_depth += 1
            if self._link_depth:
                self._link_irregular_stack.append(True)

        if tag in self._BLOCK_TAGS and tag != "a":
            self._flush_text_chunks()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._IGNORED_TAGS:
            if self._ignore_depth:
                self._ignore_depth -= 1
            return
        if self._ignore_depth:
            return

        if tag == "a" and self._link_depth:
            text = _normalize_form_text("".join(self._link_chunks))
            if text:
                self.items.append(
                    _TextItem(
                        text=text,
                        is_form_link=True,
                        is_irregular=bool(self._link_irregular_stack),
                    )
                )
            self._link_depth -= 1
            self._link_chunks = []
            self._link_irregular_stack = []
            return

        if tag in self._BLOCK_TAGS:
            self._flush_text_chunks()

        if self._irregular_context_depth:
            self._irregular_context_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._ignore_depth:
            return
        if self._link_depth:
            self._link_chunks.append(data)
            if self._irregular_context_depth:
                self._link_irregular_stack.append(True)
        else:
            self._text_chunks.append(data)

    def close(self) -> None:
        super().close()
        self._flush_text_chunks()

    def _flush_text_chunks(self) -> None:
        if not self._text_chunks:
            return
        text = _normalize_text(" ".join(self._text_chunks))
        self._text_chunks = []
        if not text:
            return
        # Split comma punctuation into its own token. It matters for cells such
        # as "hubiera, hubiese".
        parts = [part for part in re.split(r"(,)", text) if part and not part.isspace()]
        for part in parts:
            clean = _normalize_text(part)
            if clean:
                self.items.append(_TextItem(text=clean))

    @staticmethod
    def _looks_irregular(tag: str, attrs: list[tuple[str, str | None]]) -> bool:
        # SpanishDict currently presents irregular pieces in red. Their class
        # names may be generated, so use several conservative signals.
        attr_text = " ".join(
            f"{name or ''}={value or ''}".lower()
            for name, value in attrs
        )
        if "irregular" in attr_text:
            return True
        if "color" in attr_text and ("red" in attr_text or "#d" in attr_text or "rgb(" in attr_text):
            return True
        if "text-red" in attr_text or "red-" in attr_text or "color-red" in attr_text:
            return True
        # Common accessible marker fallback.
        if "aria-label" in attr_text and "irregular" in attr_text:
            return True
        return False


def import_spanishdict_conjugation(
    lemma: str,
    *,
    fetcher: Callable[[str], str] | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> ImportedVerb:
    """Fetch and parse SpanishDict conjugations for `lemma`.

    This returns a preview object only. It never writes to the app database.
    """

    clean_lemma = lemma.strip().lower()
    if not clean_lemma:
        raise SpanishDictImportError("lemma cannot be empty")

    if fetcher is None:
        html = fetch_spanishdict_html(clean_lemma, timeout_seconds=timeout_seconds)
    else:
        html = fetcher(clean_lemma)
    return parse_spanishdict_html(html, expected_lemma=clean_lemma)


def fetch_spanishdict_html(lemma: str, *, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    """Fetch SpanishDict content with a safe fallback.

    SpanishDict sometimes returns HTTP 403 to direct Python requests even with
    reasonable browser-like headers. If that happens, fall back to Jina Reader,
    which returns a text/Markdown rendering of the same public page. The parser
    accepts both raw HTML and Reader text.
    """

    clean_lemma = lemma.strip().lower()
    if not clean_lemma:
        raise SpanishDictImportError("lemma cannot be empty")

    direct_url = SPANISHDICT_CONJUGATE_URL.format(lemma=quote(clean_lemma, safe=""))
    errors: list[str] = []

    try:
        return _fetch_url(direct_url, headers=_BROWSER_HEADERS, timeout_seconds=timeout_seconds)
    except SpanishDictImportError as exc:
        errors.append(str(exc))

    reader_url = JINA_READER_PREFIX + direct_url
    try:
        return _fetch_url(reader_url, headers=_READER_HEADERS, timeout_seconds=timeout_seconds)
    except SpanishDictImportError as exc:
        errors.append(f"Reader fallback failed: {exc}")

    raise SpanishDictImportError("; ".join(errors))


def _fetch_url(url: str, *, headers: dict[str, str], timeout_seconds: int) -> str:
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(content_type, errors="replace")
    except HTTPError as exc:
        raise SpanishDictImportError(f"{url} returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise SpanishDictImportError(f"could not reach {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise SpanishDictImportError(f"request timed out for {url}") from exc


def parse_spanishdict_html(html: str, *, expected_lemma: str | None = None) -> ImportedVerb:
    items = _extract_items(html)
    if not items:
        raise SpanishDictImportError("SpanishDict page did not contain readable text")

    page_lemma = _guess_page_lemma(items, expected_lemma)
    warnings: list[str] = []

    participles = _parse_participles(items, warnings)
    forms = empty_verb_forms()

    for spec in _SECTION_SPECS:
        _parse_section(items, spec, forms, warnings)

    non_empty_forms = sum(1 for value in forms.values() if value.get("form") is not None)
    non_empty_participles = sum(1 for value in participles.values() if value.get("form") is not None)
    if non_empty_forms == 0 and non_empty_participles == 0:
        raise SpanishDictImportError("no conjugation forms were found on the page")

    _warn_for_missing_people(forms, warnings)
    if not any(value.get("is_irregular") for value in forms.values()) and not any(
        value.get("is_irregular") for value in participles.values()
    ):
        warnings.append(
            "No irregular markup was detected. The forms may still be correct, but red irregularity marking was not found."
        )

    return ImportedVerb(
        lemma=page_lemma,
        participles={
            key: ImportedForm(
                form=value["form"],
                is_irregular=bool(value["is_irregular"]),
            )
            for key, value in participles.items()
        },
        forms={
            key: ImportedForm(
                form=value["form"],
                is_irregular=bool(value["is_irregular"]),
            )
            for key, value in forms.items()
        },
        warnings=warnings,
    )


def _extract_items(html: str) -> list[_TextItem]:
    # Jina Reader returns text/Markdown, not HTML. Also, if a direct fetch ever
    # gives a plain text error or simplified rendering, the line parser gives us
    # a better failure mode than one giant token.
    if _looks_like_plain_text_or_markdown(html):
        return _extract_items_from_plain_text(html)

    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()
    items = [
        _TextItem(_normalize_text(item.text), item.is_form_link, item.is_irregular)
        for item in parser.items
        if _normalize_text(item.text)
    ]
    if len(items) <= 3:
        fallback_items = _extract_items_from_plain_text(html)
        if len(fallback_items) > len(items):
            return fallback_items
    return items


def _looks_like_plain_text_or_markdown(content: str) -> bool:
    sample = content[:2000].lstrip()
    if not sample:
        return True
    if sample.startswith(("Title:", "URL Source:", "Markdown Content:", "# ", "## ")):
        return True
    # If there are almost no tags in a large response, treat it as text.
    return sample.count("<") < 3 and "\n" in sample


def _extract_items_from_plain_text(text: str) -> list[_TextItem]:
    text = unescape(text or "")
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    # Convert Markdown links to visible text.
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)

    items: list[_TextItem] = []
    for raw_line in text.splitlines():
        line = _clean_plain_text_line(raw_line)
        if not line:
            continue
        if "|" in line:
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells and all(re.fullmatch(r":?-{2,}:?", cell.replace(" ", "")) for cell in cells if cell):
                continue
            for cell in cells:
                _append_plain_text_cell(items, cell)
        else:
            _append_plain_text_cell(items, line)
    return items


def _clean_plain_text_line(line: str) -> str:
    line = _normalize_text(line)
    if not line:
        return ""
    if line.startswith(("Title:", "URL Source:", "Markdown Content:")):
        return ""
    line = re.sub(r"^#{1,6}\s*", "", line)
    line = re.sub(r"^[-*+]\s+", "", line)
    line = re.sub(r"^>\s*", "", line)
    line = line.strip()
    # Drop common markdown table separator rows.
    if re.fullmatch(r"[:|\-\s]+", line) and "-" in line:
        return ""
    return line


def _append_plain_text_cell(items: list[_TextItem], cell: str) -> None:
    cell = _normalize_text(cell)
    if not cell:
        return
    # SpanishDict/Jina may return label lines as "Present :". Keep these as
    # one item because participle parsing accepts the trailing colon.
    if _norm_key(cell).rstrip(":") in {"present", "past"}:
        items.append(_TextItem(text=cell))
        return
    # Preserve comma alternatives as separate tokens so row parsing can join
    # them into one cell: "hubiera, hubiese".
    parts = [part for part in re.split(r"(,)", cell) if part and not part.isspace()]
    for part in parts:
        clean = _normalize_text(part)
        if clean:
            items.append(_TextItem(text=clean, is_form_link=False, is_irregular=False))


def _guess_page_lemma(items: list[_TextItem], expected_lemma: str | None) -> str:
    if expected_lemma:
        # If the expected lemma appears anywhere in the page title/header stream,
        # trust it. Otherwise still return it but let the parse continue; some
        # SpanishDict pages redirect inflected forms to infinitives.
        return expected_lemma.strip().lower()
    for item in items[:30]:
        text = item.text.strip().lower()
        if re.fullmatch(r"[a-záéíóúüñ]+(?:se)?", text):
            return text
    return ""


def _parse_participles(items: list[_TextItem], warnings: list[str]) -> dict[str, dict[str, object]]:
    participles = empty_participles()
    start = _find_item(items, lambda item: _norm_key(item.text) == "participles")
    if start is None:
        warnings.append("Participles section was not found.")
        return participles

    next_section = _find_next_section_start(items, start + 1)
    limit = next_section if next_section is not None else min(len(items), start + 30)
    index = start + 1
    while index < limit:
        label = _norm_key(items[index].text).rstrip(":").strip()
        if label in PARTICIPLE_TYPES:
            form_item = _next_form_item(items, index + 1, limit)
            if form_item is not None:
                participles[label] = _item_to_payload(form_item)
                index = form_item[0] + 1
                continue
        index += 1
    return participles


@dataclass(frozen=True)
class _SectionSpec:
    heading_prefix: str
    group_code: str
    column_labels: tuple[str, ...]
    tense_codes: tuple[str, ...]
    row_labels: tuple[str, ...]


_STANDARD_ROW_LABELS = (
    "yo",
    "tú",
    "vos",
    "él/ella/Ud.",
    "nosotros",
    "vosotros",
    "ellos/ellas/Uds.",
)

_IMPERATIVE_ROW_LABELS = (
    "yo",
    "tú",
    "vos",
    "Ud.",
    "nosotros",
    "vosotros",
    "Uds.",
)

_SECTION_SPECS = (
    _SectionSpec(
        heading_prefix="Indicative of",
        group_code="indicative",
        column_labels=("Present", "Preterite", "Imperfect", "Conditional", "Future"),
        tense_codes=EXPECTED_TENSE_CODES_BY_GROUP["indicative"],
        row_labels=_STANDARD_ROW_LABELS,
    ),
    _SectionSpec(
        heading_prefix="Subjunctive of",
        group_code="subjunctive",
        column_labels=("Present", "Imperfect", "Future"),
        tense_codes=EXPECTED_TENSE_CODES_BY_GROUP["subjunctive"],
        row_labels=_STANDARD_ROW_LABELS,
    ),
    _SectionSpec(
        heading_prefix="Imperative of",
        group_code="imperative",
        column_labels=("Affirmative", "Negative"),
        tense_codes=EXPECTED_TENSE_CODES_BY_GROUP["imperative"],
        row_labels=_IMPERATIVE_ROW_LABELS,
    ),
    _SectionSpec(
        heading_prefix="Progressive of",
        group_code="progressive",
        column_labels=("Present", "Preterite", "Imperfect", "Conditional", "Future"),
        tense_codes=EXPECTED_TENSE_CODES_BY_GROUP["progressive"],
        row_labels=_STANDARD_ROW_LABELS,
    ),
    _SectionSpec(
        heading_prefix="Perfect of",
        group_code="perfect",
        column_labels=("Present", "Preterite", "Past", "Conditional", "Future"),
        tense_codes=EXPECTED_TENSE_CODES_BY_GROUP["perfect"],
        row_labels=_STANDARD_ROW_LABELS,
    ),
    _SectionSpec(
        heading_prefix="Perfect Subjunctive of",
        group_code="perfect_subjunctive",
        column_labels=("Present", "Past", "Future"),
        tense_codes=EXPECTED_TENSE_CODES_BY_GROUP["perfect_subjunctive"],
        row_labels=_STANDARD_ROW_LABELS,
    ),
    _SectionSpec(
        heading_prefix="Informal Future of",
        group_code="informal_future",
        column_labels=("Informal Future",),
        tense_codes=EXPECTED_TENSE_CODES_BY_GROUP["informal_future"],
        row_labels=_STANDARD_ROW_LABELS,
    ),
)


def _parse_section(
    items: list[_TextItem],
    spec: _SectionSpec,
    forms: dict[tuple[str, str], dict[str, object]],
    warnings: list[str],
) -> None:
    start = _find_section_start(items, spec.heading_prefix)
    if start is None:
        warnings.append(f"{spec.heading_prefix} section was not found.")
        return

    columns_start = _find_column_sequence(items, start + 1, spec.column_labels)
    if columns_start is None:
        warnings.append(f"{spec.heading_prefix} columns were not found.")
        return

    section_end = _find_next_section_start(items, start + 1)
    if section_end is None:
        section_end = len(items)

    row_positions: dict[str, int] = {}
    for row_label in spec.row_labels:
        position = _find_row_label(items, columns_start + len(spec.column_labels), section_end, row_label)
        if position is not None:
            row_positions[row_label] = position

    sorted_positions = sorted(row_positions.items(), key=lambda pair: pair[1])
    for row_label, row_start in sorted_positions:
        row_end = section_end
        for _other_label, other_position in sorted_positions:
            if other_position > row_start:
                row_end = other_position
                break
        person_code = _person_code_for_label(row_label)
        cells = _parse_row_cells(items[row_start + 1 : row_end], expected_count=len(spec.tense_codes))
        if len(cells) < len(spec.tense_codes):
            warnings.append(
                f"{spec.heading_prefix} row {row_label} had {len(cells)} forms, expected {len(spec.tense_codes)}."
            )
        for tense_code, cell in zip(spec.tense_codes, cells):
            forms[(tense_code, person_code)] = cell


def _parse_row_cells(row_items: list[_TextItem], *, expected_count: int) -> list[dict[str, object]]:
    form_tokens: list[_TextItem] = []
    for item in row_items:
        text = item.text.strip()
        if not text:
            continue
        if text == ",":
            form_tokens.append(item)
        elif _is_form_candidate(item):
            form_tokens.append(item)

    cells: list[dict[str, object]] = []
    index = 0
    while index < len(form_tokens) and len(cells) < expected_count:
        item = form_tokens[index]
        if item.text == ",":
            index += 1
            continue
        form_text, irregular = _form_text_from_item(item)
        index += 1

        alternatives = [form_text] if form_text is not None else []
        while index + 1 < len(form_tokens) and form_tokens[index].text == ",":
            next_item = form_tokens[index + 1]
            if next_item.text == ",":
                break
            next_text, next_irregular = _form_text_from_item(next_item)
            if next_text is not None:
                alternatives.append(next_text)
            irregular = irregular or next_irregular
            index += 2

        if form_text is None and not alternatives:
            cells.append({"form": None, "is_irregular": False})
        else:
            cells.append(
                normalize_irregular_payload(
                    {
                        "form": ", ".join(alternatives),
                        "is_irregular": irregular,
                    }
                )
            )
    return cells


def _warn_for_missing_people(forms: dict[tuple[str, str], dict[str, object]], warnings: list[str]) -> None:
    for person_code in PERSON_CODES:
        person_count = sum(1 for (_tense, person), value in forms.items() if person == person_code and value.get("form"))
        if person_count == 0:
            warnings.append(f"No forms were found for {person_code}; they were left empty.")


def _find_section_start(items: list[_TextItem], heading_prefix: str) -> int | None:
    prefix = _norm_key(heading_prefix)
    return _find_item(items, lambda item: _norm_key(item.text).startswith(prefix))


def _find_next_section_start(items: list[_TextItem], start: int) -> int | None:
    headings = tuple(_norm_key(spec.heading_prefix) for spec in _SECTION_SPECS)
    return _find_item(items, lambda item: _norm_key(item.text).startswith(headings), start=start)


def _find_column_sequence(items: list[_TextItem], start: int, labels: tuple[str, ...]) -> int | None:
    normalized_labels = tuple(_norm_key(label) for label in labels)
    max_start = len(items) - len(labels) + 1
    for index in range(start, max_start):
        candidate = tuple(_norm_key(items[index + offset].text) for offset in range(len(labels)))
        if candidate == normalized_labels:
            return index
    return None


def _find_row_label(items: list[_TextItem], start: int, end: int, row_label: str) -> int | None:
    expected = _norm_person_label(row_label)
    for index in range(start, end):
        if _norm_person_label(items[index].text) == expected:
            return index
    return None


def _find_item(items: list[_TextItem], predicate: Callable[[_TextItem], bool], *, start: int = 0) -> int | None:
    for index in range(start, len(items)):
        if predicate(items[index]):
            return index
    return None


def _next_form_item(items: list[_TextItem], start: int, end: int) -> tuple[int, _TextItem] | None:
    for index in range(start, end):
        if _is_form_candidate(items[index]):
            return index, items[index]
    return None


def _is_form_candidate(item: _TextItem) -> bool:
    text = item.text.strip()
    if not text:
        return False
    if text == "-":
        return True
    if item.is_form_link:
        return True
    # Fixture/test and fallback mode for pages where forms are plain text.
    if re.search(r"[a-záéíóúüñ]", text, re.IGNORECASE) and not _is_non_form_label(text):
        return True
    return False


def _is_non_form_label(text: str) -> bool:
    key = _norm_key(text).rstrip(":")
    labels = {
        "participles",
        "present",
        "past",
        "preterite",
        "imperfect",
        "conditional",
        "future",
        "affirmative",
        "negative",
        "informal future",
        "include vos",
        "include vosotros",
        "irregularities are in red",
    }
    labels.update(_norm_key(row) for row in _STANDARD_ROW_LABELS)
    labels.update(_norm_key(row) for row in _IMPERATIVE_ROW_LABELS)
    return key in labels or key.endswith(" of estar") or " of " in key


def _item_to_payload(indexed_item: tuple[int, _TextItem]) -> dict[str, object]:
    _index, item = indexed_item
    form, irregular = _form_text_from_item(item)
    return normalize_irregular_payload({"form": form, "is_irregular": irregular})


def _form_text_from_item(item: _TextItem) -> tuple[str | None, bool]:
    text = _normalize_form_text(item.text)
    if text in {"", "-", "—", "–"}:
        return None, False
    return text, item.is_irregular


def _person_code_for_label(label: str) -> str:
    normalized = _norm_person_label(label)
    mapping = {
        "yo": "yo",
        "tu": "tu",
        "vos": "vos",
        "el/ella/ud": "el_ella_usted",
        "ud": "el_ella_usted",
        "nosotros": "nosotros",
        "vosotros": "vosotros",
        "ellos/ellas/uds": "ellos_ellas_ustedes",
        "uds": "ellos_ellas_ustedes",
    }
    if normalized not in mapping:
        raise SpanishDictImportError(f"unknown person label: {label}")
    return mapping[normalized]


def _norm_person_label(text: str) -> str:
    text = _normalize_text(text).lower()
    replacements = str.maketrans({
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
    })
    text = text.translate(replacements).replace(".", "")
    return text


def _norm_key(text: str) -> str:
    return _normalize_text(text).lower().strip()


def _normalize_text(text: str) -> str:
    text = unescape(text or "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_form_text(text: str) -> str:
    text = _normalize_text(text)
    text = re.sub(r"\s+([,;:.!?])", r"\1", text)
    text = re.sub(r"([,;:.!?])\s*", r"\1 ", text)
    text = _normalize_text(text)
    # Repair the most common artifact from SpanishDict's red-letter markup as
    # seen in text extraction: forms can appear as "est á s" or "est uvi ste".
    # The raw HTML usually concatenates these correctly, but this makes copied
    # fixtures and fallback text safer.
    repair_patterns = [
        (r"\besto\s+y\b", "estoy"),
        (r"\best\s+([áé])\s*([sn]?)\b", r"est\1\2"),
        (r"\best\s+oy\b", "estoy"),
        (r"\best\s+(uve|uvo)\b", r"est\1"),
        (r"\best\s+uvi\s+(steis|ste|mos)\b", r"estuvi\1"),
        (r"\best\s+uvié\s+(ramos|semos|remos)\b", r"estuvié\1"),
        (r"\best\s+uvie\s+(ra|ras|ran|rais|ron|se|ses|sen|seis|re|res|ren|reis)\b", r"estuvie\1"),
        (r"\bhubi\s+(steis|ste|mos)\b", r"hubi\1"),
        (r"\bhubié\s+(ramos|semos|remos)\b", r"hubié\1"),
        (r"\bhubie\s+(ra|ras|ran|rais|ron|se|ses|sen|seis|re|res|ren|reis)\b", r"hubie\1"),
    ]
    previous = None
    while previous != text:
        previous = text
        for pattern, replacement in repair_patterns:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return _normalize_text(text)
