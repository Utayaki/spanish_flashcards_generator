from __future__ import annotations

import random
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from drills.inflection.cloze import EXAMPLES_PER_FORM, REGENERATE_BELOW_COUNT
from drills.inflection.corpus import CorpusError, find_examples, warm_corpus_index
from drills.inflection.storage import (
    append_examples,
    count_examples_for_record,
    ensure_source_sentence_column,
    list_complete_form_keys,
    list_used_source_sentences,
    pending_word_forms,
)
from drills.inflection.word_forms import snapshot_has_inflection_tables

_registry_lock = threading.Lock()
_jobs: dict[int, "GenerationJob"] = {}


@dataclass
class GenerationProgress:
    completed: int = 0
    total: int = 0
    already_generated: int = 0
    current_word_form: str | None = None
    generating: bool = False
    stopped: bool = False
    error: str | None = None
    started_at: float | None = None
    cancel_requested: bool = False
    indexing_corpus: bool = False
    search_log: str = ""
    corpus_file_index: int = 0
    corpus_file_total: int = 0
    corpus_file_name: str | None = None
    corpus_entry_processed: int = 0
    corpus_entry_total: int = 0

    def eta_seconds(self) -> int | None:
        if self.completed <= 0 or self.total <= self.completed:
            return 0 if self.total <= self.completed else None
        if self.started_at is None:
            return None
        elapsed = time.monotonic() - self.started_at
        avg = elapsed / self.completed
        remaining = self.total - self.completed
        return max(0, int(round(avg * remaining)))

    def estimated_completion_at(self) -> str | None:
        eta = self.eta_seconds()
        if eta is None:
            return None
        completion = datetime.now(timezone.utc) + timedelta(seconds=eta)
        return completion.strftime("%Y-%m-%dT%H:%M:%fZ")


@dataclass
class GenerationJob:
    collection_id: int
    snapshot_path: Path
    progress: GenerationProgress = field(default_factory=GenerationProgress)
    _thread: threading.Thread | None = None
    stream_lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> None:
        if self.progress.generating:
            return
        self.progress.generating = True
        self.progress.error = None
        self.progress.stopped = False
        self.progress.cancel_requested = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def request_stop(self) -> None:
        self.progress.cancel_requested = True

    def _reset_corpus_progress(self) -> None:
        self.progress.corpus_file_index = 0
        self.progress.corpus_file_name = None
        self.progress.corpus_entry_processed = 0
        self.progress.corpus_entry_total = 0

    def _run(self) -> None:
        try:
            if not snapshot_has_inflection_tables(self.snapshot_path):
                raise CorpusError(
                    "collection snapshot is missing inflection data; recreate the collection"
                )

            with sqlite3.connect(self.snapshot_path) as connection:
                connection.row_factory = sqlite3.Row
                if not _has_inflection_fsrs_schema(connection):
                    raise CorpusError(
                        "collection snapshot uses an outdated inflection drill schema; "
                        "recreate the collection"
                    )
                ensure_source_sentence_column(connection)
                connection.commit()
                used_sentences = list_used_source_sentences(connection)
                pending = pending_word_forms(connection)
                random.shuffle(pending)
                complete_count = len(list_complete_form_keys(connection))

            self.progress.already_generated = complete_count
            self.progress.total = len(pending)
            self.progress.completed = 0
            self.progress.started_at = time.monotonic()

            with self.stream_lock:
                self.progress.indexing_corpus = True
                self.progress.corpus_file_total = 0
                self._reset_corpus_progress()

            def on_file_indexed(
                file_index: int, file_total: int, file_name: str, line_count: int
            ) -> None:
                with self.stream_lock:
                    self.progress.corpus_file_index = file_index
                    self.progress.corpus_file_total = file_total
                    self.progress.corpus_file_name = file_name
                    self.progress.corpus_entry_processed = 0
                    self.progress.corpus_entry_total = line_count

            warm_corpus_index(on_file_indexed=on_file_indexed)

            with self.stream_lock:
                self.progress.indexing_corpus = False
                self._reset_corpus_progress()

            for record in pending:
                if self.progress.cancel_requested:
                    self.progress.stopped = True
                    break

                with sqlite3.connect(self.snapshot_path) as connection:
                    connection.row_factory = sqlite3.Row
                    current_count = count_examples_for_record(connection, record)
                    if current_count >= REGENERATE_BELOW_COUNT:
                        continue
                    needed = EXAMPLES_PER_FORM - current_count

                self.progress.current_word_form = record["word_form"]
                with self.stream_lock:
                    self.progress.search_log = ""
                    self._reset_corpus_progress()

                found_count = 0

                def on_sentence_found(sentence: str) -> None:
                    nonlocal found_count
                    found_count += 1
                    with self.stream_lock:
                        self.progress.search_log += f"{found_count}. {sentence}\n"

                def on_file_progress(
                    file_index: int, file_total: int, file_name: str
                ) -> None:
                    with self.stream_lock:
                        self.progress.corpus_file_index = file_index
                        self.progress.corpus_file_total = file_total
                        self.progress.corpus_file_name = file_name
                        self.progress.corpus_entry_processed = 0

                def on_entry_progress(entry_index: int, entry_total: int) -> None:
                    with self.stream_lock:
                        self.progress.corpus_entry_processed = entry_index
                        self.progress.corpus_entry_total = entry_total

                examples = find_examples(
                    record["word_form"],
                    target_count=needed,
                    used_sentences=used_sentences,
                    on_sentence_found=on_sentence_found,
                    on_file_progress=on_file_progress,
                    on_entry_progress=on_entry_progress,
                    cancel_check=lambda: self.progress.cancel_requested,
                )
                with sqlite3.connect(self.snapshot_path) as connection:
                    connection.row_factory = sqlite3.Row
                    connection.execute("BEGIN")
                    _, saved_sentences = append_examples(
                        connection, record=record, examples=examples
                    )
                    connection.commit()
                used_sentences.update(saved_sentences)
                self.progress.completed += 1

        except CorpusError as exc:
            if self.progress.cancel_requested:
                self.progress.stopped = True
            else:
                self.progress.error = str(exc)
        except Exception as exc:
            self.progress.error = f"generation failed: {exc}"
        finally:
            self.progress.generating = False
            if self.progress.error is None and not self.progress.stopped:
                self.progress.indexing_corpus = False
                self.progress.current_word_form = None


def _has_inflection_fsrs_schema(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM sqlite_master
        WHERE type = 'table' AND name = 'inflection_word_forms'
        """
    ).fetchone()
    return row is not None and int(row[0]) > 0


def get_job(collection_id: int) -> GenerationJob | None:
    with _registry_lock:
        return _jobs.get(collection_id)


def start_generation(collection_id: int, snapshot_path: Path) -> GenerationJob:
    with _registry_lock:
        existing = _jobs.get(collection_id)
        if existing is not None and existing.progress.generating:
            return existing

        job = GenerationJob(collection_id=collection_id, snapshot_path=snapshot_path)
        _jobs[collection_id] = job
        job.start()
        return job


def stop_generation(collection_id: int) -> bool:
    with _registry_lock:
        job = _jobs.get(collection_id)
        if job is None or not job.progress.generating:
            return False
        job.request_stop()
        return True


def get_progress(collection_id: int) -> dict[str, Any]:
    job = get_job(collection_id)
    if job is None:
        return {
            "generating": False,
            "completed": 0,
            "total": 0,
            "already_generated": 0,
            "current_word_form": None,
            "eta_seconds": None,
            "estimated_completion_at": None,
            "stopped": False,
            "error": None,
            "indexing_corpus": False,
            "search_log": "",
            "corpus_file_index": 0,
            "corpus_file_total": 0,
            "corpus_file_name": None,
            "corpus_entry_processed": 0,
            "corpus_entry_total": 0,
        }
    progress = job.progress
    with job.stream_lock:
        return {
            "generating": progress.generating,
            "completed": progress.completed,
            "total": progress.total,
            "already_generated": progress.already_generated,
            "current_word_form": progress.current_word_form,
            "eta_seconds": progress.eta_seconds(),
            "estimated_completion_at": progress.estimated_completion_at(),
            "stopped": progress.stopped,
            "error": progress.error,
            "indexing_corpus": progress.indexing_corpus,
            "search_log": progress.search_log,
            "corpus_file_index": progress.corpus_file_index,
            "corpus_file_total": progress.corpus_file_total,
            "corpus_file_name": progress.corpus_file_name,
            "corpus_entry_processed": progress.corpus_entry_processed,
            "corpus_entry_total": progress.corpus_entry_total,
        }
