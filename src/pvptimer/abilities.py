"""Ability data model and the pure rules around it (no Qt)."""
import re
from dataclasses import dataclass, replace
from typing import Any, Iterable

SLOTS = ("Q", "W", "E", "R", "D", "F", "Passive")
MAX_COOLDOWN_S = 600.0
RESERVED_WORD = "clear"
CATEGORIES = ("weapon", "armor_item", "armor_ability", "custom")  # "custom" = added by the user
FORMAT_VERSION = 1


def normalize_phrase(text: str) -> str:
    """Lowercase, turn punctuation (except apostrophes) into spaces, collapse whitespace."""
    cleaned = re.sub(r"[^a-z0-9'\s]", " ", text.lower())
    return " ".join(cleaned.split())


def make_id(name: str, existing: Iterable[str]) -> str:
    taken = set(existing)
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "ability"
    candidate, n = base, 2
    while candidate in taken:
        candidate = f"{base}_{n}"
        n += 1
    return candidate


@dataclass(frozen=True)
class Ability:
    id: str
    name: str
    slot: str
    cooldown_s: float
    phrases: tuple[str, ...]
    category: str = "custom"

    def normalized(self) -> "Ability":
        phrases = tuple(p for p in (normalize_phrase(x) for x in self.phrases) if p)
        return replace(self, name=self.name.strip(), phrases=phrases)

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "slot": self.slot, "cooldown_s": self.cooldown_s,
                "phrases": list(self.phrases), "category": self.category}

    @staticmethod
    def from_json(data: dict[str, Any]) -> "Ability":
        phrases = data["phrases"]
        if not isinstance(phrases, list):
            raise TypeError("phrases must be a list")
        return Ability(
            id=str(data["id"]),
            name=str(data["name"]),
            slot=str(data["slot"]),
            cooldown_s=float(data["cooldown_s"]),
            phrases=tuple(str(p) for p in phrases),
            category=str(data.get("category", "custom")),  # files from before categories existed
        ).normalized()


def validate(ability: Ability, others: Iterable[Ability]) -> list[str]:
    """Every problem with `ability`, given the current list (its own saved copy is ignored)."""
    a = ability.normalized()
    errors: list[str] = []
    if not a.name:
        errors.append("Name is required.")
    if a.slot not in SLOTS:
        errors.append(f"Slot must be one of: {', '.join(SLOTS)}.")
    if a.category not in CATEGORIES:
        errors.append(f"Category must be one of: {', '.join(CATEGORIES)}.")
    if not (0 < a.cooldown_s <= MAX_COOLDOWN_S):
        errors.append(f"Cooldown must be greater than 0 and at most {MAX_COOLDOWN_S:g} seconds.")
    if not a.phrases:
        errors.append("At least one phrase is required.")
    owners = {p: o for o in others if o.id != a.id for p in o.normalized().phrases}
    seen: set[str] = set()
    for p in a.phrases:
        if p in seen:
            errors.append(f"Phrase '{p}' is listed twice.")
            continue
        seen.add(p)
        if p.split()[0] == RESERVED_WORD:
            errors.append(f"Phrase '{p}' starts with the reserved word '{RESERVED_WORD}'.")
        if p in owners:
            errors.append(f"Phrase '{p}' is already used by {owners[p].name}.")
    return errors


def merge(defaults: Iterable[Ability], user: Iterable[Ability], deleted_ids: Iterable[str]) -> list[Ability]:
    """Effective list: defaults (replaced by same-id user entries), then user-only entries,
    minus deleted ids."""
    user_by_id = {a.id: a for a in user}
    deleted = set(deleted_ids)
    result: list[Ability] = []
    default_ids: set[str] = set()
    for d in defaults:
        default_ids.add(d.id)
        if d.id not in deleted:
            result.append(user_by_id.get(d.id, d))
    result.extend(a for a in user_by_id.values() if a.id not in default_ids and a.id not in deleted)
    return result


def phrase_owners(abilities: Iterable[Ability]) -> dict[str, list[Ability]]:
    owners: dict[str, list[Ability]] = {}
    for a in abilities:
        for p in a.phrases:
            owners.setdefault(p, []).append(a)
    return owners


def parse_ability_file(data: Any) -> tuple[list[Ability], list[str]]:
    """Parse {"version", "abilities", optional "deleted_ids"}.
    Raises ValueError/TypeError/KeyError on a bad shape."""
    if not isinstance(data, dict) or data.get("version") != FORMAT_VERSION:
        raise ValueError(f"not a PVPTimer ability file (expected version {FORMAT_VERSION})")
    abilities = [Ability.from_json(item) for item in data["abilities"]]
    deleted = [str(x) for x in data.get("deleted_ids", [])]
    return abilities, deleted


def ability_file(abilities: Iterable[Ability], deleted_ids: Iterable[str] = ()) -> dict[str, Any]:
    data: dict[str, Any] = {"version": FORMAT_VERSION, "abilities": [a.to_json() for a in abilities]}
    deleted = sorted(deleted_ids)
    if deleted:
        data["deleted_ids"] = deleted
    return data
