from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from drills.inflection.ollama import (
    OLLAMA_MODEL,
    OllamaError,
    OllamaNotRunningError,
    ensure_ollama_running,
    generate_examples,
)
from drills.inflection.storage import (
    clear_inflection_drills,
    finalize_inflection_drills,
    save_word_form_with_examples,
)
from drills.inflection.word_forms import (
    aggregate_word_forms,
    snapshot_has_inflection_tables,
)

_registry_lock = threading.Lock()
_jobs: dict[int, "GenerationJob"] = {}


@dataclass
class GenerationProgress:
    completed: int = 0
    total: int = 0
    current_word_form: str | None = None
    generating: bool = False
    error: str | None = None


@dataclass
class GenerationJob:
    collection_id: int
    snapshot_path: Path
    progress: GenerationProgress = field(default_factory=GenerationProgress)
    _thread: threading.Thread | None = None

    def start(self) -> None:
        if self.progress.generating:
            return
        self.progress.generating = True
        self.progress.error = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            ensure_ollama_running()
            if not snapshot_has_inflection_tables(self.snapshot_path):
                raise OllamaError(
                    "collection snapshot is missing inflection data; recreate the collection"
                )

            with sqlite3.connect(self.snapshot_path) as connection:
                connection.row_factory = sqlite3.Row
                word_forms = aggregate_word_forms(connection)
                connection.execute("BEGIN")
                clear_inflection_drills(connection)
                connection.commit()

            self.progress.total = len(word_forms)
            self.progress.completed = 0

            for record in word_forms:
                self.progress.current_word_form = record["word_form"]
                examples = generate_examples(record)
                with sqlite3.connect(self.snapshot_path) as connection:
                    connection.row_factory = sqlite3.Row
                    connection.execute("BEGIN")
                    save_word_form_with_examples(connection, record=record, examples=examples)
                    connection.commit()
                self.progress.completed += 1

            with sqlite3.connect(self.snapshot_path) as connection:
                connection.execute("BEGIN")
                finalize_inflection_drills(
                    connection,
                    total_word_forms=len(word_forms),
                    model_name=OLLAMA_MODEL,
                )
                connection.commit()
        except OllamaNotRunningError as exc:
            self.progress.error = str(exc)
        except OllamaError as exc:
            self.progress.error = str(exc)
        except Exception as exc:
            self.progress.error = f"generation failed: {exc}"
        finally:
            self.progress.generating = False
            self.progress.current_word_form = None


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


def get_progress(collection_id: int) -> dict[str, Any]:
    job = get_job(collection_id)
    if job is None:
        return {
            "generating": False,
            "completed": 0,
            "total": 0,
            "current_word_form": None,
            "error": None,
        }
    return {
        "generating": job.progress.generating,
        "completed": job.progress.completed,
        "total": job.progress.total,
        "current_word_form": job.progress.current_word_form,
        "error": job.progress.error,
    }
