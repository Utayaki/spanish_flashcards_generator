from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from drills.inflection.ollama import (
    OllamaError,
    OllamaNotRunningError,
    ensure_ollama_running,
    generate_examples,
)
from drills.inflection.storage import (
    clear_form_examples,
    is_form_complete,
    pending_word_forms,
    save_examples,
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
    ollama_stream: str = ""

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

    def _run(self) -> None:
        try:
            ensure_ollama_running()
            if not snapshot_has_inflection_tables(self.snapshot_path):
                raise OllamaError(
                    "collection snapshot is missing inflection data; recreate the collection"
                )

            with sqlite3.connect(self.snapshot_path) as connection:
                connection.row_factory = sqlite3.Row
                if not _has_denormalized_examples_schema(connection):
                    raise OllamaError(
                        "collection snapshot uses an outdated inflection drill schema; "
                        "recreate the collection"
                    )
                pending = pending_word_forms(connection)
                complete_count = _count_complete_forms_quick(connection)

            self.progress.already_generated = complete_count
            self.progress.total = len(pending)
            self.progress.completed = 0
            self.progress.started_at = time.monotonic()

            for record in pending:
                if self.progress.cancel_requested:
                    self.progress.stopped = True
                    break

                with sqlite3.connect(self.snapshot_path) as connection:
                    connection.row_factory = sqlite3.Row
                    if is_form_complete(connection, record):
                        continue

                self.progress.current_word_form = record["word_form"]
                with self.stream_lock:
                    self.progress.ollama_stream = ""

                def append_chunk(chunk: str) -> None:
                    with self.stream_lock:
                        self.progress.ollama_stream += chunk

                examples = generate_examples(
                    record,
                    on_chunk=append_chunk,
                    cancel_check=lambda: self.progress.cancel_requested,
                )
                with sqlite3.connect(self.snapshot_path) as connection:
                    connection.row_factory = sqlite3.Row
                    connection.execute("BEGIN")
                    clear_form_examples(connection, record)
                    save_examples(connection, record=record, examples=examples)
                    connection.commit()
                self.progress.completed += 1

        except OllamaNotRunningError as exc:
            self.progress.error = str(exc)
        except OllamaError as exc:
            if self.progress.cancel_requested:
                self.progress.stopped = True
            else:
                self.progress.error = str(exc)
        except Exception as exc:
            self.progress.error = f"generation failed: {exc}"
        finally:
            self.progress.generating = False
            if self.progress.error is None and not self.progress.stopped:
                self.progress.current_word_form = None


def _has_denormalized_examples_schema(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM sqlite_master
        WHERE type = 'table' AND name = 'inflection_drill_word_forms'
        """
    ).fetchone()
    if row is not None and int(row[0]) > 0:
        return False
    row = connection.execute(
        """
        SELECT COUNT(*) AS count
        FROM pragma_table_info('inflection_drill_examples')
        WHERE name = 'headword'
        """
    ).fetchone()
    return row is not None and int(row[0]) > 0


def _count_complete_forms_quick(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*) FROM (
            SELECT 1
            FROM inflection_drill_examples
            GROUP BY lexical_item_id, word_form, form_descriptor
            HAVING COUNT(*) >= 5
        )
        """
    ).fetchone()
    return int(row[0]) if row is not None else 0


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
            "ollama_stream": "",
        }
    progress = job.progress
    with job.stream_lock:
        ollama_stream = progress.ollama_stream
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
        "ollama_stream": ollama_stream,
    }
