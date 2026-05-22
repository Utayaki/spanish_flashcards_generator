from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

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


class StartPage(QWidget):
    """Class-first start page.

    Flow:
    1. Show only word-class buttons.
    2. After class selection, show lemma input.
    3. Search only the selected class.
    4. Show matches under "Already added ...".
    5. Clicking a match opens it.
    6. Pressing Enter opens an exact match or creates a new word.
    """

    open_word_requested = pyqtSignal(int)
    created_word = pyqtSignal(int)

    def __init__(self, database: SpanishWordDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.database = database
        self.selected_word_type: str | None = None
        self.current_results: list[dict[str, Any]] = []

        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(120)
        self.search_timer.timeout.connect(self._run_search)

        self._build_ui()
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

    def select_word_type(self, word_type: str) -> None:
        self.selected_word_type = word_type
        self.current_results = []
        self.selected_class_label.setText(class_button_label(word_type))
        self.already_added_label.setText(already_added_title(word_type))
        self.lemma_input.clear()
        self._clear_results()
        self._set_entry_visible(True)
        self._update_create_button()
        self.lemma_input.setFocus()

    def _set_entry_visible(self, visible: bool) -> None:
        self.entry_panel.setVisible(visible)

    def _on_lemma_changed(self) -> None:
        self._update_create_button()
        self.search_timer.start()

    def _run_search(self) -> None:
        if self.selected_word_type is None:
            self.current_results = []
            self._render_results()
            return

        query = normalize_lemma_input(self.lemma_input.text())
        if not query:
            self.current_results = []
            self._render_results()
            return

        self.current_results = self.database.search_words(self.selected_word_type, query)
        self._render_results()
        self._update_create_button()

    def _render_results(self) -> None:
        self._clear_results()
        query = normalize_lemma_input(self.lemma_input.text())

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
