from __future__ import annotations

from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import QComboBox, QLabel, QLineEdit, QMessageBox, QVBoxLayout, QWidget

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
from widgets.editor_action_bar import EditorActionBar
from widgets.form_card import FormCard
from widgets.header_bar import HeaderBar
from widgets.inflection_grid import NominalInflectionGrid


_VALID_GENDER_VALUES = {value for value, _label in GENDER_CHOICES}


class NominalEditor(QWidget):
    """Editor for nouns, adjectives, and determiners.

    Existing words update their row. New words stay as drafts until "Save and
    go back" creates the complete database payload.
    """

    back_requested = pyqtSignal()
    saved = pyqtSignal(int)

    @classmethod
    def existing(
        cls,
        database: SpanishWordDatabase,
        *,
        word_id: int,
        parent: QWidget | None = None,
    ) -> "NominalEditor":
        return cls(database, word_id=word_id, parent=parent)

    @classmethod
    def new_draft(
        cls,
        database: SpanishWordDatabase,
        *,
        word_type: str,
        lemma: str,
        parent: QWidget | None = None,
    ) -> "NominalEditor":
        return cls(database, word_type=word_type, lemma=lemma, parent=parent)

    def __init__(
        self,
        database: SpanishWordDatabase,
        *,
        word_id: int | None = None,
        word_type: str | None = None,
        lemma: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if (word_id is None) == (word_type is None):
            raise ValueError("NominalEditor requires exactly one of word_id or word_type")

        self.database = database
        self.word_id = word_id
        self._loading = False
        self._dirty = DirtyState()

        if word_id is not None:
            self.word_data = self.database.load_word(word_id)
            self.word_type = ensure_nominal_word_type(str(self.word_data["word_type"]))
        else:
            assert word_type is not None
            self.word_type = ensure_nominal_word_type(word_type)
            self.word_data = {
                "id": None,
                "lemma": lemma,
                "english": "",
                "word_type": self.word_type,
                "nominal": {"gender_availability": "", "inflections": None},
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
        self.lemma_input.textChanged.connect(self._on_title_source_changed)
        self.lemma_input.textChanged.connect(self._on_any_field_changed)

        self.english_input = QLineEdit(self)
        self.english_input.setObjectName("EditorLineEdit")
        self.english_input.setPlaceholderText("Write the English definition first")
        self.english_input.textChanged.connect(self._on_any_field_changed)

        self.gender_combo = QComboBox(self)
        self.gender_combo.setObjectName("GenderAvailabilityCombo")
        self.gender_combo.addItem("Choose gender / forms…", None)
        for value, label in GENDER_CHOICES:
            self.gender_combo.addItem(label, value)
        self.gender_combo.currentIndexChanged.connect(self._on_gender_changed)

        self.base_card.add_row(0, "Lemma", self.lemma_input)
        self.base_card.add_row(1, "English", self.english_input)
        self.base_card.add_row(2, gender_field_label(self.word_type), self.gender_combo)
        root.addWidget(self.base_card)

        self.helper_label = QLabel("", self)
        self.helper_label.setObjectName("HelperText")
        root.addWidget(self.helper_label)

        self.inflections_card = FormCard("Inflections", self)
        self.inflection_grid = NominalInflectionGrid(self)
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

            nominal = data.get("nominal", {})
            gender_availability = str(nominal.get("gender_availability") or "")
            self._set_combo_value(gender_availability)
            if gender_availability in _VALID_GENDER_VALUES:
                self.inflection_grid.set_gender_availability(gender_availability)
            self.inflection_grid.set_forms(nested_inflections_to_tuple_map(nominal.get("inflections")))
            self._update_title()
        finally:
            self._loading = False

    def _set_combo_value(self, value: str) -> None:
        index = self.gender_combo.findData(value) if value else 0
        if index < 0:
            index = 0
        self.gender_combo.setCurrentIndex(index)

    def _current_gender_availability(self) -> str:
        value = self.gender_combo.currentData()
        return str(value) if value is not None else ""

    def _has_english_definition(self) -> bool:
        return bool(self.english_input.text().strip())

    def _has_gender_choice(self) -> bool:
        return self._current_gender_availability() in _VALID_GENDER_VALUES

    def _is_valid_for_save(self) -> bool:
        return bool(self.lemma_input.text().strip()) and self._has_english_definition() and self._has_gender_choice()

    def _sync_availability(self) -> None:
        has_english = self._has_english_definition()
        has_gender = self._has_gender_choice()
        self.gender_combo.setEnabled(has_english)
        self.inflections_card.setVisible(has_english and has_gender)
        self.inflections_card.setEnabled(has_english and has_gender)

        if not has_english:
            self.helper_label.setText("Enter the English definition to unlock gender/forms.")
            self.helper_label.setVisible(True)
        elif not has_gender:
            self.helper_label.setText("Choose gender/forms to unlock the inflections table.")
            self.helper_label.setVisible(True)
        else:
            self.helper_label.setVisible(False)

    def _on_gender_changed(self) -> None:
        if not self._loading and self._has_gender_choice():
            self.inflection_grid.set_gender_availability(self._current_gender_availability())
        self._on_any_field_changed()

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
        title = editor_title(self.word_type, self.lemma_input.text())
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

    def collect_payload(self) -> NominalSavePayload:
        return NominalSavePayload.from_inputs(
            lemma=self.lemma_input.text(),
            english=self.english_input.text(),
            gender_availability=self._current_gender_availability(),
            forms=self.inflection_grid.forms(),
        )

    def save(self) -> bool:
        if not self._is_valid_for_save():
            QMessageBox.warning(self, "Cannot save", "Complete the English definition and gender/forms choice first.")
            return False

        if not self.is_new and not self.is_dirty():
            return True

        try:
            payload = self.collect_payload()
            if self.is_new:
                self.word_id = self.database.create_nominal_word(
                    lemma=payload.lemma,
                    word_type=self.word_type,
                    english=payload.english,
                    gender_availability=payload.gender_availability,
                    forms=payload.forms,
                )
                self.lemma_input.setReadOnly(False)
            else:
                assert self.word_id is not None
                self.database.save_word_base(self.word_id, lemma=payload.lemma, english=payload.english)
                self.database.save_nominal_details(self.word_id, payload.gender_availability)
                self.database.save_nominal_inflections(self.word_id, payload.forms)
        except (NominalEditorStateError, ValidationError, DatabaseError) as exc:
            QMessageBox.warning(self, "Cannot save", str(exc))
            return False

        self._mark_clean()
        assert self.word_id is not None
        self.saved.emit(self.word_id)
        return True

    def save_and_go_back(self) -> None:
        if self.save():
            self.back_requested.emit()
