from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QComboBox, QLabel, QLineEdit, QMessageBox, QVBoxLayout, QWidget

from controllers.editor_dirty_state import DirtyState
from controllers.other_editor_state import (
    OTHER_SUBTYPE_LABELS,
    OTHER_SUBTYPES,
    OtherEditorStateError,
    OtherSavePayload,
    editor_title,
    ensure_other_word_type,
)
from database import DatabaseError, SpanishWordDatabase, ValidationError
from widgets.editor_action_bar import EditorActionBar
from widgets.form_card import FormCard
from widgets.header_bar import HeaderBar


_VALID_SUBTYPES = set(OTHER_SUBTYPES)


class OtherEditor(QWidget):
    """Minimal editor for non-inflective 'other' words."""

    back_requested = pyqtSignal()
    saved = pyqtSignal(int)

    @classmethod
    def existing(
        cls,
        database: SpanishWordDatabase,
        *,
        word_id: int,
        parent: QWidget | None = None,
    ) -> "OtherEditor":
        return cls(database, word_id=word_id, parent=parent)

    @classmethod
    def new_draft(
        cls,
        database: SpanishWordDatabase,
        *,
        lemma: str,
        parent: QWidget | None = None,
    ) -> "OtherEditor":
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
                "other": {"subtype": ""},
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

        self.form_card = FormCard("Base", self)
        self.lemma_input = QLineEdit(self)
        self.lemma_input.setObjectName("EditorLineEdit")
        self.lemma_input.setReadOnly(self.is_new)
        self.lemma_input.textChanged.connect(self._update_title)
        self.lemma_input.textChanged.connect(self._on_any_field_changed)

        self.english_input = QLineEdit(self)
        self.english_input.setObjectName("EditorLineEdit")
        self.english_input.setPlaceholderText("Write the English definition first")
        self.english_input.textChanged.connect(self._on_any_field_changed)

        self.subtype_combo = QComboBox(self)
        self.subtype_combo.setObjectName("OtherSubtypeCombo")
        self.subtype_combo.addItem("Choose subtype…", None)
        for subtype in OTHER_SUBTYPES:
            self.subtype_combo.addItem(OTHER_SUBTYPE_LABELS[subtype], subtype)
        self.subtype_combo.currentIndexChanged.connect(self._on_any_field_changed)

        self.form_card.add_row(0, "Lemma", self.lemma_input)
        self.form_card.add_row(1, "English", self.english_input)
        self.form_card.add_row(2, "Subtype", self.subtype_combo)
        root.addWidget(self.form_card)

        self.helper_label = QLabel("", self)
        self.helper_label.setObjectName("HelperText")
        root.addWidget(self.helper_label)

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
            self._set_combo_value(str(other.get("subtype") or ""))
            self._update_title()
        finally:
            self._loading = False

    def _set_combo_value(self, value: str) -> None:
        index = self.subtype_combo.findData(value) if value else 0
        if index < 0:
            index = 0
        self.subtype_combo.setCurrentIndex(index)

    def _current_subtype(self) -> str:
        value = self.subtype_combo.currentData()
        return str(value) if value is not None else ""

    def _has_english_definition(self) -> bool:
        return bool(self.english_input.text().strip())

    def _has_subtype_choice(self) -> bool:
        return self._current_subtype() in _VALID_SUBTYPES

    def _is_valid_for_save(self) -> bool:
        return bool(self.lemma_input.text().strip()) and self._has_english_definition() and self._has_subtype_choice()

    def _sync_availability(self) -> None:
        has_english = self._has_english_definition()
        has_subtype = self._has_subtype_choice()
        self.subtype_combo.setEnabled(has_english)

        if not has_english:
            self.helper_label.setText("Enter the English definition to unlock subtype.")
            self.helper_label.setVisible(True)
        elif not has_subtype:
            self.helper_label.setText("Choose a subtype before saving.")
            self.helper_label.setVisible(True)
        else:
            self.helper_label.setVisible(False)

    def _current_snapshot(self) -> tuple[object, ...]:
        return (
            self.lemma_input.text().strip(),
            self.english_input.text().strip(),
            self._current_subtype(),
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
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.save_shortcut.activated.connect(self.save_and_go_back)

        self.back_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
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
            subtype=self._current_subtype(),
        )

    def save(self) -> bool:
        if not self._is_valid_for_save():
            QMessageBox.warning(self, "Cannot save", "Complete the English definition and subtype first.")
            return False

        if not self.is_new and not self.is_dirty():
            return True

        try:
            payload = self.collect_payload()
            if self.is_new:
                self.word_id = self.database.create_other_word(
                    lemma=payload.lemma,
                    english=payload.english,
                    subtype=payload.subtype,
                )
                self.lemma_input.setReadOnly(False)
            else:
                assert self.word_id is not None
                self.database.save_word_base(self.word_id, lemma=payload.lemma, english=payload.english)
                self.database.save_other_details(self.word_id, payload.subtype)
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
