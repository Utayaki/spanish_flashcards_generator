from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

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
from widgets.header_bar import HeaderBar


class OtherEditor(QWidget):
    """Minimal editor for non-inflective 'other' words."""

    back_requested = pyqtSignal()
    deleted = pyqtSignal(int)
    saved = pyqtSignal(int)

    def __init__(
        self,
        database: SpanishWordDatabase,
        word_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.database = database
        self.word_id = word_id
        self.word_data = self.database.load_word(word_id)
        ensure_other_word_type(str(self.word_data["word_type"]))
        self._loading = False
        self._dirty = DirtyState()

        self._build_ui()
        self._load_data(self.word_data)
        self._mark_clean()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        self.header = HeaderBar(parent=self)
        self.header.save_requested.connect(self.save)
        root.addWidget(self.header)

        form = QWidget(self)
        form_layout = QGridLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(8)
        form_layout.setVerticalSpacing(8)

        self.lemma_input = QLineEdit(self)
        self.lemma_input.setObjectName("EditorLineEdit")
        self.lemma_input.textChanged.connect(self._update_title)
        self.lemma_input.textChanged.connect(self._on_any_field_changed)

        self.english_input = QLineEdit(self)
        self.english_input.setObjectName("EditorLineEdit")
        self.english_input.textChanged.connect(self._on_any_field_changed)

        self.subtype_combo = QComboBox(self)
        self.subtype_combo.setObjectName("OtherSubtypeCombo")
        for subtype in OTHER_SUBTYPES:
            self.subtype_combo.addItem(OTHER_SUBTYPE_LABELS[subtype], subtype)
        self.subtype_combo.currentIndexChanged.connect(self._on_any_field_changed)

        form_layout.addWidget(self._label("Lemma"), 0, 0)
        form_layout.addWidget(self.lemma_input, 0, 1)
        form_layout.addWidget(self._label("English"), 1, 0)
        form_layout.addWidget(self.english_input, 1, 1)
        form_layout.addWidget(self._label("Subtype"), 2, 0)
        form_layout.addWidget(self.subtype_combo, 2, 1)
        root.addWidget(form)

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.setSpacing(8)

        self.back_button = QPushButton("Back", self)
        self.back_button.clicked.connect(self.request_back)

        self.delete_button = QPushButton("Delete", self)
        self.delete_button.setObjectName("DeleteButton")
        self.delete_button.clicked.connect(self.delete)

        self.save_button = QPushButton("Save", self)
        self.save_button.setObjectName("BottomSaveButton")
        self.save_button.clicked.connect(self.save)

        button_row.addWidget(self.back_button)
        button_row.addStretch(1)
        button_row.addWidget(self.delete_button)
        button_row.addWidget(self.save_button)
        root.addLayout(button_row)
        root.addStretch(1)

        self._install_shortcuts()

    def _label(self, text: str) -> QLabel:
        label = QLabel(text, self)
        label.setObjectName("FormCardFieldLabel")
        return label

    def _load_data(self, data: dict[str, Any]) -> None:
        self._loading = True
        try:
            self.lemma_input.setText(str(data.get("lemma", "")))
            self.english_input.setText(str(data.get("english", "")))
            other = data.get("other", {})
            self._set_combo_value(str(other.get("subtype", "unknown")))
            self._update_title()
        finally:
            self._loading = False

    def _set_combo_value(self, value: str) -> None:
        index = self.subtype_combo.findData(value)
        if index < 0:
            index = self.subtype_combo.findData("unknown")
        self.subtype_combo.setCurrentIndex(index)

    def _current_subtype(self) -> str:
        return str(self.subtype_combo.currentData())

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
        self._dirty.update(self._current_snapshot())
        self._sync_dirty_ui()

    def is_dirty(self) -> bool:
        return self._dirty.is_dirty

    def _sync_dirty_ui(self) -> None:
        can_save = self._dirty.can_save
        self.header.set_save_enabled(can_save)
        self.save_button.setEnabled(can_save)
        self._update_title()

    def _update_title(self) -> None:
        title = editor_title(self.lemma_input.text())
        if self.is_dirty():
            title = f"{title} *"
        self.header.set_title(title)

    def _install_shortcuts(self) -> None:
        self.save_shortcut = QShortcut(QKeySequence.StandardKey.Save, self)
        self.save_shortcut.activated.connect(self.save)

        self.back_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self.back_shortcut.activated.connect(self.request_back)

    def request_back(self) -> None:
        if self.is_dirty():
            reply = QMessageBox.question(
                self,
                "Discard unsaved changes",
                "Discard unsaved changes and go back?",
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
        if not self.is_dirty():
            return True

        try:
            payload = self.collect_payload()
            self.database.save_word_base(
                self.word_id,
                lemma=payload.lemma,
                english=payload.english,
            )
            self.database.save_other_details(self.word_id, payload.subtype)
        except (OtherEditorStateError, ValidationError, DatabaseError) as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
            return False

        self._mark_clean()
        self.saved.emit(self.word_id)
        return True

    def delete(self) -> None:
        reply = QMessageBox.question(
            self,
            "Delete word",
            f"Delete {self.lemma_input.text().strip() or 'this word'}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if self.database.delete_word(self.word_id):
            self.deleted.emit(self.word_id)
        else:
            QMessageBox.warning(self, "Delete failed", "This word was not found in the database.")
