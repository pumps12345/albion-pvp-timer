"""Ability editor window: list, add, edit, delete, import/export and test voice phrases."""
from pathlib import Path
from typing import Callable, Iterable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .abilities import MAX_COOLDOWN_S, SLOTS, Ability
from .store import AbilityStore

COLUMNS = ("Name", "Slot", "Cooldown", "Voice phrases", "Status")
STATUS_COLUMN = 4
TEST_TIMEOUT_MS = 10_000
UnknownWords = Callable[[Iterable[str]], set[str]]


def ability_status(ability: Ability, unknown_words: UnknownWords, duplicates: set[str]) -> tuple[str, str]:
    """(Status column text, tooltip)."""
    words = unknown_words(ability.phrases)
    if words:
        return ("⚠ word", "Not in the speech model's vocabulary: " + ", ".join(sorted(words))
                + ". Respell with common words (e.g. 'hell ion').")
    dups = sorted(set(ability.phrases) & duplicates)
    if dups:
        return "⚠ dup", "Also used by another ability: " + ", ".join(dups)
    return "✓", ""


def describe_test_result(text: str, matched: Ability | None, editing_id: str, dirty: bool) -> str:
    if not text:
        message = "Heard nothing — try again."
    elif matched is None:
        message = f'Heard: "{text}" → ✗ no match'
    elif matched.id == editing_id:
        message = f'Heard: "{text}" → ✓ matches {matched.name}'
    else:
        message = f'Heard: "{text}" → matches a different ability: {matched.name}'
    if dirty:
        message += "  (unsaved changes can't be heard until you Save)"
    return message


class EditorWindow(QWidget):
    test_requested = Signal()

    def __init__(self, store: AbilityStore, unknown_words: UnknownWords) -> None:
        super().__init__()
        self.setWindowTitle("PVPTimer – Ability Editor")
        self.resize(780, 600)
        self._store = store
        self._unknown_words = unknown_words
        self._editing: Ability | None = None  # None = a new, unsaved ability

        # toolbar
        self.add_button = QPushButton("+ Add")
        self.delete_button = QPushButton("Delete")
        self.import_button = QPushButton("Import…")
        self.export_button = QPushButton("Export…")
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search names and phrases")
        toolbar = QHBoxLayout()
        for widget in (self.add_button, self.delete_button, self.import_button, self.export_button):
            toolbar.addWidget(widget)
        toolbar.addStretch(1)
        toolbar.addWidget(self.search_edit)

        # table
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        # form
        self.form_title = QLabel()
        self.name_edit = QLineEdit()
        self.slot_combo = QComboBox()
        self.slot_combo.addItems(SLOTS)
        self.cooldown_spin = QDoubleSpinBox()
        self.cooldown_spin.setRange(0.1, MAX_COOLDOWN_S)
        self.cooldown_spin.setDecimals(1)
        self.cooldown_spin.setSuffix(" s")
        self.phrases_edit = QPlainTextEdit()
        self.phrases_edit.setPlaceholderText("One phrase per line, e.g.\nblood letter e\nblood e")
        self.phrases_edit.setFixedHeight(90)
        self.errors_label = QLabel()
        self.errors_label.setStyleSheet("color: #dc2626;")
        self.errors_label.setWordWrap(True)
        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Slot", self.slot_combo)
        form.addRow("Cooldown", self.cooldown_spin)
        form.addRow("Phrases", self.phrases_edit)
        form.addRow(self.errors_label)

        self.test_button = QPushButton("🎤 Test phrase")
        self.test_label = QLabel()
        self.test_label.setWordWrap(True)
        test_row = QHBoxLayout()
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.test_label, 1)

        self.save_button = QPushButton("Save")
        self.revert_button = QPushButton("Revert")
        buttons_row = QHBoxLayout()
        buttons_row.addStretch(1)
        buttons_row.addWidget(self.save_button)
        buttons_row.addWidget(self.revert_button)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.form_title)
        layout.addLayout(form)
        layout.addLayout(test_row)
        layout.addLayout(buttons_row)

        self._test_timeout = QTimer(self)
        self._test_timeout.setSingleShot(True)
        self._test_timeout.setInterval(TEST_TIMEOUT_MS)
        self._test_timeout.timeout.connect(self._on_test_timeout)

        self.add_button.clicked.connect(self._add)
        self.delete_button.clicked.connect(self._delete)
        self.import_button.clicked.connect(self._import)
        self.export_button.clicked.connect(self._export)
        self.search_edit.textChanged.connect(self._apply_filter)
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.name_edit.textChanged.connect(lambda *_: self._validate_form())
        self.phrases_edit.textChanged.connect(lambda *_: self._validate_form())
        self.slot_combo.currentIndexChanged.connect(lambda *_: self._validate_form())
        self.cooldown_spin.valueChanged.connect(lambda *_: self._validate_form())
        self.save_button.clicked.connect(self._save)
        self.revert_button.clicked.connect(self._revert)
        self.test_button.clicked.connect(self._request_test)
        store.abilities_changed.connect(self.refresh)

        self.refresh()
        self._load_form(None)

    # table --------------------------------------------------------------
    def refresh(self) -> None:
        abilities = self._store.abilities()
        duplicates = self._store.duplicate_phrases()
        self.table.blockSignals(True)
        self.table.setRowCount(len(abilities))
        for row, ability in enumerate(abilities):
            status, tip = ability_status(ability, self._unknown_words, duplicates)
            cells = (ability.name, ability.slot, f"{ability.cooldown_s:.1f} s", ", ".join(ability.phrases), status)
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, ability.id)
                if col == STATUS_COLUMN:
                    item.setToolTip(tip)
                self.table.setItem(row, col, item)
        self._select_row_for(self._editing.id if self._editing else None)
        self.table.blockSignals(False)
        self._apply_filter(self.search_edit.text())
        if self._editing is not None and self._store.get(self._editing.id) is None:
            self._load_form(None)

    def _select_row_for(self, ability_id: str | None) -> None:
        self.table.clearSelection()
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).data(Qt.ItemDataRole.UserRole) == ability_id:
                self.table.selectRow(row)
                return

    def _apply_filter(self, text: str) -> None:
        needle = text.casefold().strip()
        for row in range(self.table.rowCount()):
            haystack = f"{self.table.item(row, 0).text()} {self.table.item(row, 3).text()}".casefold()
            self.table.setRowHidden(row, bool(needle) and needle not in haystack)

    def _on_selection(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if rows:
            ability_id = self.table.item(rows[0].row(), 0).data(Qt.ItemDataRole.UserRole)
            self._load_form(self._store.get(ability_id))

    # form ---------------------------------------------------------------
    def form_ability(self) -> Ability:
        return Ability(
            id=self._editing.id if self._editing else "",
            name=self.name_edit.text(),
            slot=self.slot_combo.currentText(),
            cooldown_s=round(self.cooldown_spin.value(), 1),
            phrases=tuple(self.phrases_edit.toPlainText().splitlines()),
        )

    def is_dirty(self) -> bool:
        current = self.form_ability().normalized()
        if self._editing is None:
            return bool(current.name or current.phrases)
        return current != self._editing

    def _load_form(self, ability: Ability | None) -> None:
        self._editing = ability
        widgets = (self.name_edit, self.slot_combo, self.cooldown_spin, self.phrases_edit)
        for widget in widgets:
            widget.blockSignals(True)
        self.name_edit.setText(ability.name if ability else "")
        self.slot_combo.setCurrentText(ability.slot if ability else "E")
        self.cooldown_spin.setValue(ability.cooldown_s if ability else 10.0)
        self.phrases_edit.setPlainText("\n".join(ability.phrases) if ability else "")
        for widget in widgets:
            widget.blockSignals(False)
        self.form_title.setText(f"Edit: {ability.name}" if ability else "New ability")
        self.delete_button.setEnabled(ability is not None)
        self._test_timeout.stop()
        self.test_label.setText("")
        self._validate_form()

    def _validate_form(self) -> None:
        dirty = self.is_dirty()
        errors = self._store.validate(self.form_ability()) if dirty else []
        self.errors_label.setText("\n".join(errors))
        self.save_button.setEnabled(dirty and not errors)
        self.revert_button.setEnabled(dirty)

    def _save(self) -> None:
        try:
            stored = self._store.upsert(self.form_ability())
        except ValueError as exc:
            self.errors_label.setText(str(exc))
            return
        self._editing = stored
        self.refresh()
        self._load_form(stored)

    def _revert(self) -> None:
        self._load_form(self._editing)

    def _add(self) -> None:
        self.table.clearSelection()
        self._load_form(None)
        self.name_edit.setFocus()

    def _delete(self) -> None:
        if self._editing is None:
            return
        answer = QMessageBox.question(self, "Delete ability", f"Delete '{self._editing.name}'?")
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._store.delete(self._editing.id)
        self._load_form(None)

    # import / export ----------------------------------------------------
    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import abilities", "", "Ability lists (*.json)")
        if not path:
            return
        try:
            result = self._store.import_file(Path(path), self._ask_replace)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.warning(self, "Import failed", f"Could not import {Path(path).name}: {exc}")
            return
        lines = [f"Added: {len(result.added)}", f"Replaced: {len(result.replaced)}",
                 f"Kept existing: {len(result.kept)}"]
        if result.skipped:
            lines.append("Skipped:\n  " + "\n  ".join(result.skipped))
        QMessageBox.information(self, "Import finished", "\n".join(lines))

    def _ask_replace(self, existing: Ability, incoming: Ability) -> bool:
        answer = QMessageBox.question(
            self, "Ability already exists",
            f"'{existing.name}' already exists. Replace it with the imported version "
            f"({incoming.cooldown_s:g} s: {', '.join(incoming.phrases)})?")
        return answer == QMessageBox.StandardButton.Yes

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export abilities", "pvptimer-abilities.json",
                                              "Ability lists (*.json)")
        if not path:
            return
        try:
            self._store.export_file(Path(path))
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", f"Could not write {path}: {exc}")

    # phrase test ----------------------------------------------------------
    def _request_test(self) -> None:
        self.test_label.setText("Hold your push-to-talk key and speak…")
        self._test_timeout.start()
        self.test_requested.emit()

    def show_test_result(self, text: str, matched: Ability | None) -> None:
        if not self._test_timeout.isActive():
            return  # not waiting for a test result
        self._test_timeout.stop()
        editing_id = self._editing.id if self._editing else ""
        self.test_label.setText(describe_test_result(text, matched, editing_id, self.is_dirty()))

    def _on_test_timeout(self) -> None:
        self.test_label.setText("No speech heard within 10 seconds.")
