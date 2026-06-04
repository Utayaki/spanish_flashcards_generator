from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QComboBox, QLabel, QLineEdit, QMessageBox, QVBoxLayout, QWidget

from controllers.editor_dirty_state import DirtyState, freeze_mapping
from controllers.other_editor_state import (
    OtherEditorStateError,
    OtherSavePayload,
    editor_title,
    ensure_other_word_type,
    nested_inflections_to_tuple_map,
)
from database import DatabaseError, SpanishWordDatabase, ValidationError
from widgets.editor_action_bar import EditorActionBar
from widgets.form_card import FormCard
from widgets.header_bar import HeaderBar
from widgets.inflection_grid import NominalInflectionGrid


class OtherEditor(QWidget):
    """Editor for words outside noun/adjective/verb.

    Other words either have no inflections or use the same 2×2 masc/fem ×
    singular/plural grid.
    """

    back_requested = pyqtSignal()
    saved = pyqtSignal(int)

    @classmethod
    def existing(cls, database: SpanishWordDatabase, *, word_id: int, parent: QWidget | None = None) -> "OtherEditor":
        return cls(database, word_id=word_id, parent=parent)

    @classmethod
    def new_draft(cls, database: SpanishWordDatabase, *, lemma: str, parent: QWidget | None = None) -> "OtherEditor":
        return cls(database, lemma=lemma, parent=parent)

    def __init__(
        self,
        database: SpanishWordDatabase,
        *,
        word_id: int | None = None,
        lemma: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.word_id = word_id
        self._loading = False
        self._dirty = DirtyState()

        if word_id is not None:
            self.word_data = self.database.load_word(word_id)
            ensure_other_word_type(str(self.word_data["word_type"]))
        else:
            self.word_data = {
                "id": None,
                "lemma": lemma,
                "english": "",
                "word_type": "other",
                "other": {"has_inflections": None, "inflections": None},
            }

        self._build_ui()
        self._load_data(self.word_data)
        self._mark_clean()
        self._sync_availability()
        self._sync_dirty_ui()

    @property
    def is_new(self) -> bool:
        return self.word_id is None

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        self.header = HeaderBar(parent=self)
        root.addWidget(self.header)

        self.base_card = FormCard("Base", self)
        self.lemma_input = QLineEdit(self)
        self.lemma_input.setObjectName("EditorLineEdit")
        self.lemma_input.setReadOnly(self.is_new)
        self.lemma_input.setInputMethodHints(Qt.InputMethodHint.ImhNone)
        self.lemma_input.textChanged.connect(self._update_title)
        self.lemma_input.textChanged.connect(self._on_any_field_changed)

        self.english_input = QLineEdit(self)
        self.english_input.setObjectName("EditorLineEdit")
        self.english_input.setPlaceholderText("Write the English definition first")
        self.english_input.setInputMethodHints(Qt.InputMethodHint.ImhNone)
        self.english_input.textChanged.connect(self._on_any_field_changed)

        self.has_inflections_combo = QComboBox(self)
        self.has_inflections_combo.setObjectName("OtherHasInflectionsCombo")
        self.has_inflections_combo.addItem("Choose yes/no…", None)
        self.has_inflections_combo.addItem("No inflections", False)
        self.has_inflections_combo.addItem("Has inflections", True)
        self.has_inflections_combo.currentIndexChanged.connect(self._on_has_inflections_changed)

        self.base_card.add_row(0, "Lemma", self.lemma_input)
        self.base_card.add_row(1, "English", self.english_input)
        self.base_card.add_row(2, "Has inflections?", self.has_inflections_combo)
        root.addWidget(self.base_card)

        self.helper_label = QLabel("", self)
        self.helper_label.setObjectName("HelperText")
        root.addWidget(self.helper_label)

        self.inflections_card = FormCard("Inflections", self)
        self.inflection_grid = NominalInflectionGrid(self)
        self.inflection_grid.set_gender_availability("both")
        self.inflection_grid.forms_changed.connect(self._on_any_field_changed)
        self.inflections_card.content_layout.addWidget(self.inflection_grid, 0, 0, 1, 2)
        root.addWidget(self.inflections_card)
        root.addStretch(1)

        self.action_bar = EditorActionBar(self)
        self.action_bar.discard_requested.connect(self.request_back)
        self.action_bar.save_requested.connect(self.save_and_go_back)
        root.addWidget(self.action_bar)
        self._install_shortcuts()

    def _load_data(self, data: dict[str, Any]) -> None:
        self._loading = True
        try:
            self.lemma_input.setText(str(data.get("lemma", "")))
            self.english_input.setText(str(data.get("english", "")))
            other = data.get("other", {})
            has_inflections = other.get("has_inflections")
            self._set_has_inflections_value(has_inflections if isinstance(has_inflections, bool) else None)
            self.inflection_grid.set_gender_availability("both")
            if has_inflections is True:
                self.inflection_grid.set_forms(
                    nested_inflections_to_tuple_map(other.get("inflections")),
                    explicit_none=not self.is_new,
                )
            else:
                self.inflection_grid.set_unset_empty()
            self._update_title()
        finally:
            self._loading = False

    def _set_has_inflections_value(self, value: bool | None) -> None:
        index = self.has_inflections_combo.findData(value)
        self.has_inflections_combo.setCurrentIndex(index if index >= 0 else 0)

    def _current_has_inflections(self) -> bool | None:
        value = self.has_inflections_combo.currentData()
        if value is None:
            return None
        return bool(value)

    def _has_english_definition(self) -> bool:
        return bool(self.english_input.text().strip())

    def _has_inflection_choice(self) -> bool:
        return self._current_has_inflections() is not None

    def _forms_complete(self) -> bool:
        if self._current_has_inflections() is not True:
            return True
        return self.inflection_grid.all_enabled_cells_complete()

    def _is_valid_for_save(self) -> bool:
        return (
            bool(self.lemma_input.text().strip())
            and self._has_english_definition()
            and self._has_inflection_choice()
            and self._forms_complete()
        )

    def _sync_availability(self) -> None:
        has_english = self._has_english_definition()
        choice = self._current_has_inflections()
        self.has_inflections_combo.setEnabled(has_english)
        show_grid = has_english and choice is True
        self.inflections_card.setVisible(show_grid)
        self.inflections_card.setEnabled(show_grid)

        if not has_english:
            self.helper_label.setText("Enter the English definition to unlock the inflection choice.")
            self.helper_label.setVisible(True)
        elif choice is None:
            self.helper_label.setText("Choose whether this word has inflections.")
            self.helper_label.setVisible(True)
        elif choice is True and not self._forms_complete():
            self.helper_label.setText("Every visible form must be filled or explicitly marked None.")
            self.helper_label.setVisible(True)
        else:
            self.helper_label.setVisible(False)

    def _on_has_inflections_changed(self) -> None:
        if not self._loading:
            if self._current_has_inflections() is True and self.is_new:
                self.inflection_grid.set_unset_empty()
        self._on_any_field_changed()

    def _current_snapshot(self) -> tuple[object, ...]:
        return (
            self.lemma_input.text().strip(),
            self.english_input.text().strip(),
            self._current_has_inflections(),
            freeze_mapping(self.inflection_grid.forms()),
            self.inflection_grid.all_enabled_cells_complete(),
        )

    def _mark_clean(self) -> None:
        self._dirty.mark_clean(self._current_snapshot())
        self._sync_dirty_ui()

    def _on_any_field_changed(self, *_args: object) -> None:
        if self._loading:
            return
        self._sync_availability()
        self._dirty.update(self._current_snapshot())
        self._sync_dirty_ui()

    def is_dirty(self) -> bool:
        return self._dirty.is_dirty

    def _sync_dirty_ui(self) -> None:
        can_save = self._is_valid_for_save() and (self.is_dirty() or self.is_new)
        self.action_bar.set_dirty(self.is_dirty(), is_new=self.is_new)
        self.action_bar.set_save_enabled(can_save)
        self._update_title()

    def _update_title(self) -> None:
        title = editor_title(self.lemma_input.text())
        if self.is_dirty():
            title = f"{title} *"
        self.header.set_title(title)

    def _install_shortcuts(self) -> None:
        # Do not install Ctrl-based shortcuts. On some non-English layouts,
        # AltGr is reported as Ctrl+Alt and shortcut handlers can steal normal
        # text input from QLineEdit. Escape is safe because it does not produce
        # text.
        self.back_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.back_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.back_shortcut.activated.connect(self.request_back)

    def request_back(self) -> None:
        if self.is_dirty():
            reply = QMessageBox.question(
                self,
                "Discard unsaved changes",
                "Go back without saving these changes?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.back_requested.emit()

    def collect_payload(self) -> OtherSavePayload:
        return OtherSavePayload.from_inputs(
            lemma=self.lemma_input.text(),
            english=self.english_input.text(),
            has_inflections=self._current_has_inflections(),
            forms=self.inflection_grid.forms(),
        )

    def save(self) -> bool:
        if not self._is_valid_for_save():
            QMessageBox.warning(
                self,
                "Cannot save",
                "Complete the English definition, inflection choice, and every visible form cell first.",
            )
            return False
        if not self.is_new and not self.is_dirty():
            return True
        try:
            payload = self.collect_payload()
            if self.is_new:
                self.word_id = self.database.create_other_word(
                    lemma=payload.lemma,
                    english=payload.english,
                    has_inflections=payload.has_inflections,
                    forms=payload.forms,
                )
                self.lemma_input.setReadOnly(False)
            else:
                assert self.word_id is not None
                self.database.save_word_base(self.word_id, lemma=payload.lemma, english=payload.english)
                self.database.save_other_details(self.word_id, payload.has_inflections)
                self.database.save_other_inflections(self.word_id, payload.forms)
        except (OtherEditorStateError, ValidationError, DatabaseError) as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
            return False
        self._mark_clean()
        assert self.word_id is not None
        self.saved.emit(self.word_id)
        return True

    def save_and_go_back(self) -> None:
        if self.save():
            self.back_requested.emit()
