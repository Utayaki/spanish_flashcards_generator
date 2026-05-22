from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from controllers.search_request import SearchRequestTracker
from controllers.start_page_presenter import (
    WORD_CLASS_META,
    already_added_title,
    class_button_label,
    class_singular_label,
    create_button_text,
    find_exact_match,
    highlight_match_html,
    normalize_lemma_input,
    primary_action_for_enter,
)
from database import SpanishWordDatabase


class AlreadyAddedRow(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, result: dict[str, Any], query: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.word_id = int(result["id"])
        self.setObjectName("AlreadyAddedRow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        lemma = str(result.get("lemma", ""))
        english = str(result.get("english", "")).strip()

        lemma_label = QLabel(highlight_match_html(lemma, query))
        lemma_label.setTextFormat(Qt.TextFormat.RichText)
        lemma_label.setObjectName("AlreadyAddedLemma")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)
        layout.addWidget(lemma_label)

        if english:
            english_label = QLabel(english)
            english_label.setObjectName("AlreadyAddedEnglish")
            layout.addWidget(english_label)

    def mousePressEvent(self, event):  # type: ignore[override]
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.word_id)
            event.accept()
            return
        super().mousePressEvent(event)


class SearchWorkerSignals(QObject):
    finished = pyqtSignal(int, str, str, object, object)


class SearchWorker(QRunnable):
    """Runs one same-class SQLite search outside the UI thread."""

    def __init__(
        self,
        database: SpanishWordDatabase,
        request_id: int,
        word_type: str,
        query: str,
    ) -> None:
        super().__init__()
        self.database = database
        self.request_id = request_id
        self.word_type = word_type
        self.query = query
        self.signals = SearchWorkerSignals()

    @pyqtSlot()
    def run(self) -> None:
        try:
            results = self.database.search_words(self.word_type, self.query)
            error: str | None = None
        except Exception as exc:  # defensive: never crash the GUI from a worker
            results = []
            error = str(exc)

        self.signals.finished.emit(
            self.request_id,
            self.word_type,
            self.query,
            results,
            error,
        )


class StartPage(QWidget):
    """Class-first start page with debounced threaded "Already added" search.

    Flow:
    1. Show only word-class buttons.
    2. After class selection, show lemma input.
    3. Debounce keystrokes.
    4. Search only the selected class in a worker thread.
    5. Ignore stale worker results using request IDs.
    6. Clicking a match opens it.
    7. Pressing Enter opens an exact match or creates a new word.
    """

    open_word_requested = pyqtSignal(int)
    created_word = pyqtSignal(int)

    def __init__(self, database: SpanishWordDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.selected_word_type: str | None = None
        self.current_results: list[dict[str, Any]] = []
        self.search_tracker = SearchRequestTracker()
        self.thread_pool = QThreadPool.globalInstance()
        self.is_searching = False
        self.last_search_error: str | None = None

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(120)
        self.search_timer.timeout.connect(self._start_threaded_search)

        self._build_ui()
        self._install_shortcuts()
        self._set_entry_visible(False)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        title = QLabel("Spanish Word DB")
        title.setObjectName("PageTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        self.class_buttons: dict[str, QPushButton] = {}
        self.class_button_box = QVBoxLayout()
        self.class_button_box.setSpacing(8)

        for word_type in WORD_CLASS_META:
            button = QPushButton(class_button_label(word_type))
            button.setObjectName("ClassButton")
            button.clicked.connect(lambda checked=False, wt=word_type: self.select_word_type(wt))
            self.class_buttons[word_type] = button
            self.class_button_box.addWidget(button)

        root.addLayout(self.class_button_box)

        self.entry_panel = QFrame()
        self.entry_panel.setObjectName("EntryPanel")
        entry_layout = QVBoxLayout(self.entry_panel)
        entry_layout.setContentsMargins(0, 0, 0, 0)
        entry_layout.setSpacing(8)

        self.selected_class_label = QLabel("")
        self.selected_class_label.setObjectName("SelectedClassLabel")
        entry_layout.addWidget(self.selected_class_label)

        lemma_label = QLabel("Lemma")
        lemma_label.setObjectName("FieldLabel")
        entry_layout.addWidget(lemma_label)

        self.lemma_input = QLineEdit()
        self.lemma_input.setObjectName("LemmaInput")
        self.lemma_input.textChanged.connect(self._on_lemma_changed)
        self.lemma_input.returnPressed.connect(self._on_return_pressed)
        entry_layout.addWidget(self.lemma_input)

        self.already_added_label = QLabel("")
        self.already_added_label.setObjectName("AlreadyAddedTitle")
        entry_layout.addWidget(self.already_added_label)

        self.results_box = QVBoxLayout()
        self.results_box.setSpacing(6)
        entry_layout.addLayout(self.results_box)

        self.none_label = QLabel("None")
        self.none_label.setObjectName("NoneLabel")
        self.results_box.addWidget(self.none_label)

        self.create_button = QPushButton("Create")
        self.create_button.setObjectName("CreateButton")
        self.create_button.clicked.connect(self._create_current_word)
        entry_layout.addWidget(self.create_button)

        root.addWidget(self.entry_panel)
        root.addStretch(1)

    def _install_shortcuts(self) -> None:
        self.clear_lemma_shortcut = QShortcut(QKeySequence("Ctrl+Backspace"), self)
        self.clear_lemma_shortcut.activated.connect(self.clear_lemma)

    def clear_lemma(self) -> None:
        if self.entry_panel.isVisible():
            self.lemma_input.clear()
            self.lemma_input.setFocus()

    def select_word_type(self, word_type: str) -> None:
        self.selected_word_type = word_type
        self.current_results = []
        self.is_searching = False
        self.last_search_error = None
        self.search_timer.stop()
        self.search_tracker.new_input(word_type, "")
        self.selected_class_label.setText(class_button_label(word_type))
        self.already_added_label.setText(already_added_title(word_type))
        self.lemma_input.clear()
        self._render_results()
        self._set_entry_visible(True)
        self._update_create_button()
        self.lemma_input.setFocus()

    def _set_entry_visible(self, visible: bool) -> None:
        self.entry_panel.setVisible(visible)

    def _on_lemma_changed(self) -> None:
        self.last_search_error = None
        self.current_results = []
        self.is_searching = False
        query = normalize_lemma_input(self.lemma_input.text())
        request_id = self.search_tracker.new_input(self.selected_word_type, query)

        if self.selected_word_type is None or not query:
            self.search_timer.stop()
            self._render_results()
            self._update_create_button()
            return

        # Render an immediate, minimal feedback state. The worker is only
        # launched after the debounce interval expires.
        self.is_searching = True
        self._render_results()
        self._update_create_button()
        self.search_timer.start()

    def _start_threaded_search(self) -> None:
        if self.selected_word_type is None:
            return

        query = normalize_lemma_input(self.lemma_input.text())
        if not query:
            self.is_searching = False
            self.current_results = []
            self._render_results()
            self._update_create_button()
            return

        request_id = self.search_tracker.latest_request_id
        worker = SearchWorker(self.database, request_id, self.selected_word_type, query)
        worker.signals.finished.connect(self._on_search_finished)
        self.thread_pool.start(worker)

    def _on_search_finished(
        self,
        request_id: int,
        word_type: str,
        query: str,
        results: object,
        error: object,
    ) -> None:
        if not self.search_tracker.should_apply(request_id, word_type, query):
            return

        self.is_searching = False
        self.last_search_error = str(error) if error else None
        self.current_results = list(results) if isinstance(results, list) else []
        self._render_results()
        self._update_create_button()

    def _render_results(self) -> None:
        self._clear_results()
        query = normalize_lemma_input(self.lemma_input.text())

        if self.last_search_error:
            error_label = QLabel("Search error")
            error_label.setObjectName("NoneLabel")
            self.results_box.addWidget(error_label)
            return

        if self.is_searching:
            searching_label = QLabel("Searching…")
            searching_label.setObjectName("NoneLabel")
            self.results_box.addWidget(searching_label)
            return

        if not self.current_results:
            self.none_label = QLabel("None")
            self.none_label.setObjectName("NoneLabel")
            self.results_box.addWidget(self.none_label)
            return

        for result in self.current_results:
            row = AlreadyAddedRow(result, query)
            row.clicked.connect(self.open_word_requested.emit)
            self.results_box.addWidget(row)

    def _clear_results(self) -> None:
        while self.results_box.count():
            item = self.results_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _update_create_button(self) -> None:
        if self.selected_word_type is None:
            self.create_button.setEnabled(False)
            self.create_button.setText("Create")
            return

        lemma = normalize_lemma_input(self.lemma_input.text())
        exact_match = find_exact_match(self.current_results, lemma) is not None
        self.create_button.setText(
            create_button_text(self.selected_word_type, lemma, exact_match_exists=exact_match)
        )
        self.create_button.setEnabled(bool(lemma))

    def _on_return_pressed(self) -> None:
        if self.selected_word_type is None:
            return

        action = primary_action_for_enter(self.current_results, self.lemma_input.text())
        if action.name == "open" and action.word_id is not None:
            self.open_word_requested.emit(action.word_id)
        elif action.name == "create":
            self._create_current_word()

    def _create_current_word(self) -> None:
        if self.selected_word_type is None:
            return

        lemma = normalize_lemma_input(self.lemma_input.text())
        if not lemma:
            return

        word_id = self.database.create_word(
            lemma,
            self.selected_word_type,
            english="",
            gender_availability="both",
            other_subtype="unknown",
        )
        self.created_word.emit(word_id)
        self.open_word_requested.emit(word_id)

    def current_class_label(self) -> str:
        if self.selected_word_type is None:
            return ""
        return class_singular_label(self.selected_word_type)
