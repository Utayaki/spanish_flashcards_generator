from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLineEdit, QPushButton, QWidget

from widgets.form_state import IrregularTextValue, NullableTextValue, normalize_optional_form


class NullableLineEdit(QWidget):
    """Line edit with an explicit None toggle.

    Default state is intentionally blank and not None. That means the cell is
    incomplete until the user either types a form or explicitly chooses None.
    """

    value_changed = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None, *, placeholder: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("NullableLineEdit")

        self.line_edit = QLineEdit(self)
        self.line_edit.setObjectName("NullableLineEditText")
        self.line_edit.setPlaceholderText(placeholder)
        self.line_edit.setInputMethodHints(Qt.InputMethodHint.ImhNone)

        self.none_button = QPushButton("None", self)
        self.none_button.setObjectName("NullableLineEditNoneButton")
        self.none_button.setCheckable(True)
        self.none_button.setFixedWidth(58)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._layout.addWidget(self.line_edit, 1)
        self._layout.addWidget(self.none_button)

        self.line_edit.textChanged.connect(self._emit_value_changed)
        self.none_button.toggled.connect(self._on_none_toggled)
        self._sync_enabled_state()

    def value(self) -> str | None:
        return NullableTextValue.from_widget_state(
            self.line_edit.text(),
            self.none_button.isChecked(),
        ).as_database_value()

    def set_value(self, value: str | None, *, explicit_none: bool = True) -> None:
        cleaned = normalize_optional_form(value)
        if cleaned is None:
            self.none_button.setChecked(explicit_none)
            self.line_edit.clear()
        else:
            self.none_button.setChecked(False)
            self.line_edit.setText(cleaned)
        self._sync_enabled_state()
        self._emit_value_changed()

    def set_unset_empty(self) -> None:
        """Clear the cell without choosing None."""

        self.none_button.setChecked(False)
        self.line_edit.clear()
        self._sync_enabled_state()
        self._emit_value_changed()

    def set_none(self, enabled: bool) -> None:
        self.none_button.setChecked(enabled)
        if enabled:
            self.line_edit.clear()
        self._sync_enabled_state()
        self._emit_value_changed()

    def is_none(self) -> bool:
        return self.none_button.isChecked()

    def is_complete(self) -> bool:
        return self.none_button.isChecked() or bool(self.line_edit.text().strip())

    def set_cell_enabled(self, enabled: bool, *, clear_when_disabled: bool = True) -> None:
        self.setEnabled(enabled)
        if not enabled and clear_when_disabled:
            self.set_value(None, explicit_none=True)
        self._sync_enabled_state()

    def _on_none_toggled(self, checked: bool) -> None:
        if checked:
            self.line_edit.clear()
        self._sync_enabled_state()
        self._emit_value_changed()

    def _sync_enabled_state(self) -> None:
        self.line_edit.setEnabled(not self.none_button.isChecked() and self.isEnabled())

    def changeEvent(self, event):  # type: ignore[override]
        super().changeEvent(event)
        self._sync_enabled_state()

    def _emit_value_changed(self) -> None:
        self.value_changed.emit(self.value())


class IrregularNullableLineEdit(NullableLineEdit):
    """Nullable verb/participle cell with a manual irregular flag."""

    payload_changed = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None, *, placeholder: str = "") -> None:
        super().__init__(parent, placeholder=placeholder)
        self.setObjectName("IrregularNullableLineEdit")

        self.irregular_checkbox = QCheckBox("Irregular", self)
        self.irregular_checkbox.setObjectName("IrregularCheckbox")
        self._layout.addWidget(self.irregular_checkbox)

        self.irregular_checkbox.toggled.connect(self._on_irregular_toggled)
        self.value_changed.connect(lambda _value: self._emit_payload_changed())
        self._sync_irregular_state()

    def payload(self) -> dict[str, object]:
        return IrregularTextValue.from_widget_state(
            self.line_edit.text(),
            self.none_button.isChecked(),
            self.irregular_checkbox.isChecked(),
        ).as_database_payload()

    def set_payload(self, *, form: str | None, is_irregular: bool, explicit_none: bool = True) -> None:
        self.set_value(form, explicit_none=explicit_none)
        self.irregular_checkbox.setChecked(bool(is_irregular) if self.value() is not None else False)
        self._sync_irregular_state()
        self._emit_payload_changed()

    def set_unset_empty(self) -> None:
        super().set_unset_empty()
        self.irregular_checkbox.setChecked(False)
        self._sync_irregular_state()
        self._emit_payload_changed()

    def set_irregular(self, is_irregular: bool) -> None:
        self.irregular_checkbox.setChecked(bool(is_irregular))
        self._sync_irregular_state()
        self._emit_payload_changed()

    def is_irregular(self) -> bool:
        return bool(self.payload()["is_irregular"])

    def _on_none_toggled(self, checked: bool) -> None:
        super()._on_none_toggled(checked)
        if checked:
            self.irregular_checkbox.setChecked(False)
        self._sync_irregular_state()
        self._emit_payload_changed()

    def _on_irregular_toggled(self, _checked: bool) -> None:
        self._sync_irregular_state()
        self._emit_payload_changed()

    def _sync_irregular_state(self) -> None:
        has_form = self.value() is not None
        self.irregular_checkbox.setEnabled(has_form and self.isEnabled())
        if self.irregular_checkbox.isChecked() and has_form:
            self.line_edit.setStyleSheet("color: #b00020;")
        else:
            self.line_edit.setStyleSheet("")

    def changeEvent(self, event):  # type: ignore[override]
        super().changeEvent(event)
        self._sync_irregular_state()

    def _emit_payload_changed(self) -> None:
        self.payload_changed.emit(self.payload())
