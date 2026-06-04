from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QGridLayout, QLabel, QWidget

from widgets.form_state import (
    GENDERS,
    NUMBERS,
    apply_gender_availability_to_forms,
    empty_nominal_forms,
    is_gender_enabled,
    validate_gender_availability,
)
from widgets.nullable_line_edit import NullableLineEdit


class NominalInflectionGrid(QWidget):
    """2×2 singular/plural × masculine/feminine inflection grid."""

    forms_changed = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("NominalInflectionGrid")
        self._gender_availability = "both"
        self._cells: dict[tuple[str, str], NullableLineEdit] = {}

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(6)

        layout.addWidget(QLabel(""), 0, 0)
        for col, gender in enumerate(GENDERS, start=1):
            label = QLabel(gender)
            label.setObjectName("GridHeaderLabel")
            layout.addWidget(label, 0, col)

        for row, number in enumerate(NUMBERS, start=1):
            number_label = QLabel(number)
            number_label.setObjectName("GridHeaderLabel")
            layout.addWidget(number_label, row, 0)
            for col, gender in enumerate(GENDERS, start=1):
                cell = NullableLineEdit(self)
                cell.value_changed.connect(lambda _value, n=number, g=gender: self._on_cell_changed(n, g))
                self._cells[(number, gender)] = cell
                layout.addWidget(cell, row, col)

        self.set_gender_availability("both", reset_empty=True)

    def set_gender_availability(self, gender_availability: str, *, reset_empty: bool = False) -> None:
        self._gender_availability = validate_gender_availability(gender_availability)
        for (_number, gender), cell in self._cells.items():
            enabled = is_gender_enabled(self._gender_availability, gender)
            cell.set_cell_enabled(enabled)
            if enabled and reset_empty:
                cell.set_unset_empty()
            if not enabled:
                cell.set_value(None, explicit_none=True)
        self.forms_changed.emit(self.forms())

    def gender_availability(self) -> str:
        return self._gender_availability

    def forms(self) -> dict[tuple[str, str], str | None]:
        raw = {(number, gender): cell.value() for (number, gender), cell in self._cells.items()}
        return apply_gender_availability_to_forms(raw, self._gender_availability)

    def set_forms(self, forms: dict[tuple[str, str], str | None], *, explicit_none: bool = True) -> None:
        merged = empty_nominal_forms()
        merged.update(forms)
        cleaned = apply_gender_availability_to_forms(merged, self._gender_availability)
        for key, cell in self._cells.items():
            enabled = is_gender_enabled(self._gender_availability, key[1])
            cell.set_cell_enabled(enabled, clear_when_disabled=False)
            if enabled:
                cell.set_value(cleaned[key], explicit_none=explicit_none)
            else:
                cell.set_value(None, explicit_none=True)
        self.forms_changed.emit(self.forms())

    def set_unset_empty(self) -> None:
        for (_number, gender), cell in self._cells.items():
            if is_gender_enabled(self._gender_availability, gender):
                cell.set_unset_empty()
            else:
                cell.set_value(None, explicit_none=True)
        self.forms_changed.emit(self.forms())

    def all_enabled_cells_complete(self) -> bool:
        for (_number, gender), cell in self._cells.items():
            if is_gender_enabled(self._gender_availability, gender) and not cell.is_complete():
                return False
        return True

    def cell(self, number: str, gender: str) -> NullableLineEdit:
        return self._cells[(number, gender)]

    def _on_cell_changed(self, _number: str, _gender: str) -> None:
        self.forms_changed.emit(self.forms())
