from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from controllers.editor_dirty_state import DirtyState, freeze_mapping
from controllers.nominal_editor_state import (
    GENDER_CHOICES,
    NominalEditorStateError,
    NominalSavePayload,
    editor_title,
    ensure_nominal_word_type,
    gender_field_label,
    nested_inflections_to_tuple_map,
)
from database import DatabaseError, SpanishWordDatabase, ValidationError
from widgets.form_card import FormCard
from widgets.header_bar import HeaderBar
from widgets.inflection_grid import NominalInflectionGrid


class NominalEditor(QWidget):
    """Card editor for nouns, adjectives, and determiners."""

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
        self.word_type = ensure_nominal_word_type(str(self.word_data["word_type"]))
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

        self.base_card = FormCard("Base", self)
        self.lemma_input = QLineEdit(self)
        self.lemma_input.setObjectName("EditorLineEdit")
        self.lemma_input.textChanged.connect(self._on_title_source_changed)
        self.lemma_input.textChanged.connect(self._on_any_field_changed)

        self.english_input = QLineEdit(self)
        self.english_input.setObjectName("EditorLineEdit")
        self.english_input.textChanged.connect(self._on_any_field_changed)

        self.gender_combo = QComboBox(self)
        self.gender_combo.setObjectName("GenderAvailabilityCombo")
        for value, label in GENDER_CHOICES:
            self.gender_combo.addItem(label, value)
        self.gender_combo.currentIndexChanged.connect(self._on_gender_changed)
        self.gender_combo.currentIndexChanged.connect(self._on_any_field_changed)

        self.base_card.add_row(0, "Lemma", self.lemma_input)
        self.base_card.add_row(1, "English", self.english_input)
        self.base_card.add_row(2, gender_field_label(self.word_type), self.gender_combo)
        root.addWidget(self.base_card)

        self.inflections_card = FormCard("Inflections", self)
        self.inflection_grid = NominalInflectionGrid(self)
        self.inflection_grid.forms_changed.connect(self._on_any_field_changed)
        self.inflections_card.content_layout.addWidget(self.inflection_grid, 0, 0, 1, 2)
        root.addWidget(self.inflections_card)

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

    def _load_data(self, data: dict[str, Any]) -> None:
        self._loading = True
        try:
            self.lemma_input.setText(str(data.get("lemma", "")))
            self.english_input.setText(str(data.get("english", "")))

            nominal = data.get("nominal", {})
            gender_availability = str(nominal.get("gender_availability", "both"))
            self._set_combo_value(gender_availability)
            self.inflection_grid.set_gender_availability(gender_availability)
            self.inflection_grid.set_forms(
                nested_inflections_to_tuple_map(nominal.get("inflections"))
            )
            self._update_title()
        finally:
            self._loading = False

    def _set_combo_value(self, value: str) -> None:
        index = self.gender_combo.findData(value)
        if index < 0:
            index = self.gender_combo.findData("both")
        self.gender_combo.setCurrentIndex(index)

    def _current_gender_availability(self) -> str:
        return str(self.gender_combo.currentData())

    def _on_gender_changed(self) -> None:
        if self._loading:
            return
        self.inflection_grid.set_gender_availability(self._current_gender_availability())

    def _on_title_source_changed(self) -> None:
        self._update_title()

    def _current_snapshot(self) -> tuple[object, ...]:
        return (
            self.lemma_input.text().strip(),
            self.english_input.text().strip(),
            self._current_gender_availability(),
            freeze_mapping(self.inflection_grid.forms()),
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
        title = editor_title(self.word_type, self.lemma_input.text())
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

    def collect_payload(self) -> NominalSavePayload:
        return NominalSavePayload.from_inputs(
            lemma=self.lemma_input.text(),
            english=self.english_input.text(),
            gender_availability=self._current_gender_availability(),
            forms=self.inflection_grid.forms(),
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
            self.database.save_nominal_details(
                self.word_id,
                payload.gender_availability,
            )
            self.database.save_nominal_inflections(self.word_id, payload.forms)
        except (NominalEditorStateError, ValidationError, DatabaseError) as exc:
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
