"""AbilityStore: the effective ability list, persisted as bundled defaults + per-user overrides."""
import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Signal

from .abilities import (Ability, ability_file, make_id, merge, normalize_phrase,
                        parse_ability_file, phrase_owners, validate)
from .jsonio import atomic_write_json, load_or_quarantine


@dataclass
class ImportResult:
    added: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


class AbilityStore(QObject):
    abilities_changed = Signal()

    def __init__(self, defaults_path: Path, user_path: Path) -> None:
        super().__init__()
        self._defaults_path = defaults_path
        self._user_path = user_path
        self._defaults: list[Ability] = []
        self._user: dict[str, Ability] = {}
        self._deleted: set[str] = set()
        self._effective: list[Ability] = []
        self._by_phrase: dict[str, Ability] = {}
        self.warnings: list[str] = []

    def load(self) -> None:
        self._defaults, _ = parse_ability_file(json.loads(self._defaults_path.read_text(encoding="utf-8")))
        parsed, warning = load_or_quarantine(self._user_path, parse_ability_file)
        if warning:
            self.warnings.append(warning)
        user, deleted = parsed if parsed else ([], [])
        self._user = {a.id: a for a in user}
        self._deleted = set(deleted)
        self._recompute()
        self.abilities_changed.emit()

    # queries ------------------------------------------------------------
    def abilities(self) -> list[Ability]:
        return sorted(self._effective, key=lambda a: a.name.casefold())

    def get(self, ability_id: str) -> Ability | None:
        return next((a for a in self._effective if a.id == ability_id), None)

    def match(self, text: str) -> Ability | None:
        return self._by_phrase.get(normalize_phrase(text))

    def phrases(self) -> list[str]:
        return list(self._by_phrase)

    def duplicate_phrases(self) -> set[str]:
        return {p for p, owners in phrase_owners(self._effective).items() if len(owners) > 1}

    def validate(self, ability: Ability) -> list[str]:
        return validate(ability, self._effective)

    # changes ------------------------------------------------------------
    def upsert(self, ability: Ability) -> Ability:
        """Validate and save. An empty id means a new ability; one is assigned.
        Raises ValueError listing every problem."""
        errors = self.validate(ability)
        if errors:
            raise ValueError("\n".join(errors))
        stored = ability.normalized()
        if not stored.id:
            stored = replace(stored, id=make_id(stored.name, self._all_ids()))
        self._user[stored.id] = stored
        self._deleted.discard(stored.id)
        self._commit()
        return stored

    def delete(self, ability_id: str) -> None:
        self._user.pop(ability_id, None)
        if any(d.id == ability_id for d in self._defaults):
            self._deleted.add(ability_id)
        self._commit()

    def export_file(self, path: Path) -> None:
        atomic_write_json(path, ability_file(self._effective))

    def import_file(self, path: Path, replace_existing: Callable[[Ability, Ability], bool]) -> ImportResult:
        """Add abilities from an exported file. replace_existing(existing, incoming) decides id clashes.
        Raises ValueError (or OSError) when the file is not a readable ability file."""
        incoming, _ = parse_ability_file(json.loads(path.read_text(encoding="utf-8")))
        result = ImportResult()
        for ability in incoming:
            if not ability.id:
                ability = replace(ability, id=make_id(ability.name, self._all_ids()))
            existing = self.get(ability.id)
            if existing is not None and not replace_existing(existing, ability):
                result.kept.append(ability.name)
                continue
            errors = validate(ability, self._effective)
            if errors:
                result.skipped.append(f"{ability.name}: {errors[0]}")
                continue
            self._user[ability.id] = ability
            self._deleted.discard(ability.id)
            self._recompute()
            (result.replaced if existing else result.added).append(ability.name)
        if result.added or result.replaced:
            self._commit()
        return result

    # internals ----------------------------------------------------------
    def _all_ids(self) -> set[str]:
        return {a.id for a in self._defaults} | set(self._user) | self._deleted

    def _recompute(self) -> None:
        self._effective = merge(self._defaults, self._user.values(), self._deleted)
        self._by_phrase = {}
        for a in self._effective:
            for p in a.phrases:
                self._by_phrase.setdefault(p, a)  # first owner wins if a phrase is duplicated

    def _commit(self) -> None:
        atomic_write_json(self._user_path, ability_file(self._user.values(), self._deleted))
        self._recompute()
        self.abilities_changed.emit()
