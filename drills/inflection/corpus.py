from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pyarrow.parquet as pq

from drills.inflection.cloze import try_validate_sentence

CORPUS_DIR = Path(__file__).resolve().parents[2] / "spanish_corpus"
TEXT_COLUMN = "text"
_BATCH_SIZE = 1000
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_corpus_index: list[tuple[Path, int]] | None = None
_index_lock = threading.Lock()


class CorpusError(Exception):
    pass


def _corpus_files() -> list[Path]:
    return sorted(CORPUS_DIR.glob("*.parquet"))


def _parquet_row_count(path: Path) -> int:
    parquet_file = pq.ParquetFile(path)
    schema_names = parquet_file.schema_arrow.names
    if TEXT_COLUMN not in schema_names:
        raise CorpusError(
            f"corpus file {path.name} is missing required column '{TEXT_COLUMN}'"
        )
    return parquet_file.metadata.num_rows


def _build_corpus_index(
    *,
    on_file_indexed: Callable[[int, int, str, int], None] | None = None,
) -> list[tuple[Path, int]]:
    files = _corpus_files()
    if not files:
        raise CorpusError(f"no corpus files found in {CORPUS_DIR}")

    index: list[tuple[Path, int]] = []
    file_total = len(files)
    for file_index, corpus_path in enumerate(files, start=1):
        row_count = _parquet_row_count(corpus_path)
        index.append((corpus_path, row_count))
        if on_file_indexed is not None:
            on_file_indexed(file_index, file_total, corpus_path.name, row_count)
    return index


def get_corpus_index() -> list[tuple[Path, int]]:
    global _corpus_index
    with _index_lock:
        if _corpus_index is None:
            _corpus_index = _build_corpus_index()
        return _corpus_index


def warm_corpus_index(
    *,
    on_file_indexed: Callable[[int, int, str, int], None] | None = None,
) -> list[tuple[Path, int]]:
    global _corpus_index
    with _index_lock:
        if _corpus_index is None:
            _corpus_index = _build_corpus_index(on_file_indexed=on_file_indexed)
        return _corpus_index


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]


def _iter_text_batches(path: Path, batch_size: int = _BATCH_SIZE) -> Iterator:
    parquet_file = pq.ParquetFile(path)
    if TEXT_COLUMN not in parquet_file.schema_arrow.names:
        raise CorpusError(
            f"corpus file {path.name} is missing required column '{TEXT_COLUMN}'"
        )
    yield from parquet_file.iter_batches(batch_size=batch_size, columns=[TEXT_COLUMN])


def _collect_from_text(
    text: str,
    *,
    word_form: str,
    valid_clozes: list[tuple[str, str]],
    seen: set[str],
    target_count: int,
    used_sentences: set[str] | None,
    on_sentence_found: Callable[[str], None] | None,
) -> bool:
    if word_form not in text:
        return False

    for sentence in _split_sentences(text):
        cloze = try_validate_sentence(sentence, word_form=word_form)
        if cloze is None or cloze in seen:
            continue
        normalized = sentence.strip()
        if used_sentences is not None and normalized in used_sentences:
            continue
        seen.add(cloze)
        valid_clozes.append((cloze, normalized))
        if on_sentence_found is not None:
            on_sentence_found(normalized)
        if len(valid_clozes) >= target_count:
            return True
    return False


def find_examples(
    word_form: str,
    *,
    target_count: int,
    used_sentences: set[str] | None = None,
    on_sentence_found: Callable[[str], None] | None = None,
    on_file_progress: Callable[[int, int, str], None] | None = None,
    on_entry_progress: Callable[[int, int], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> list[tuple[str, str]]:
    if target_count < 1:
        raise CorpusError("target_count must be at least 1")

    corpus_index = get_corpus_index()
    file_total = len(corpus_index)
    valid_clozes: list[tuple[str, str]] = []
    seen: set[str] = set()

    for file_index, (corpus_path, file_row_count) in enumerate(corpus_index, start=1):
        if cancel_check is not None and cancel_check():
            raise CorpusError("generation cancelled")

        if on_file_progress is not None:
            on_file_progress(file_index, file_total, corpus_path.name)

        row_in_file = 0
        for batch in _iter_text_batches(corpus_path):
            if cancel_check is not None and cancel_check():
                raise CorpusError("generation cancelled")

            for text_value in batch.column(TEXT_COLUMN).to_pylist():
                row_in_file += 1
                if on_entry_progress is not None:
                    on_entry_progress(row_in_file, file_row_count)

                if not isinstance(text_value, str) or not text_value.strip():
                    continue

                if _collect_from_text(
                    text_value,
                    word_form=word_form,
                    valid_clozes=valid_clozes,
                    seen=seen,
                    target_count=target_count,
                    used_sentences=used_sentences,
                    on_sentence_found=on_sentence_found,
                ):
                    return valid_clozes

    raise CorpusError(
        f"only {len(valid_clozes)} sentence(s) found for '{word_form}', need {target_count}"
    )
