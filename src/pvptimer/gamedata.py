"""Build PVPTimer abilities from Albion Online game data.

Reads the community dumps from https://github.com/ao-data/ao-bin-dumps (items.xml, spells.xml,
localization.json). Scope: each weapon's E ability, and the choosable active abilities of chests (R),
helmets (D) and boots (F). Pure functions; scripts/import_game_data.py downloads the files and runs them.
"""
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .abilities import MAX_COOLDOWN_S, RESERVED_WORD, Ability, make_id, normalize_phrase

TIER = "T4_"  # every item line exists at tier 4; higher tiers share its abilities
TIER_PREFIX = re.compile(r"^(Beginner's|Novice's|Journeyman's|Adept's|Expert's|Master's|Grandmaster's|Elder's)\s+")
WEAPON_E_SLOT = "3"
ARMOR = {"armor": ("armors", "R"), "head": ("head", "D"), "shoes": ("shoes", "F")}  # slottype -> (shop, key)
MIN_PART = 3  # shortest piece accepted when splitting a compound word
# Albion words the small Vosk model doesn't know, mapped to sound-alikes it does. The recognizer only
# picks between your phrases, so "hal bird" is what it matches when you say "halberd".
SPOKEN = {
    "badon": "baden", "bracers": "bracer", "camlann": "cam lan", "cestus": "says us",
    "clarent": "clarence", "druidic": "druid", "galatine": "gala teen", "glaive": "glade",
    "halberd": "hal bird", "judicator": "judy cater", "mage": "madge", "maulers": "mauler", "mistpiercer": "mist pierce",
    "requite": "re quite", "rotcaller": "rot caller", "ursine": "er sign",
}


@dataclass(frozen=True)
class SpellInfo:
    cooldown_s: float
    name_key: str              # localization key of the English name
    multi_stage: bool = False  # cooldown came from a recast stage: worth checking in game


@dataclass(frozen=True)
class GameAbility:
    item_name: str
    ability_name: str
    slot: str
    cooldown_s: float
    kind: str  # "weapon" or "armor"
    verify: bool = False  # cooldown read from a recast stage


def english_strings(localization: dict[str, Any]) -> dict[str, str]:
    strings = {}
    for unit in localization["tmx"]["body"]["tu"]:
        variants = unit.get("tuv", [])
        for variant in variants if isinstance(variants, list) else [variants]:
            if variant.get("@xml:lang") == "EN-US" and variant.get("seg"):
                strings[unit["@tuid"]] = variant["seg"]
    return strings


def spell_info(spells: ET.Element) -> dict[str, SpellInfo]:
    """Active and toggle spells that have a cooldown. Two-stage abilities (cast, then recast) keep
    their cooldown on a later stage, so the `multispell` chain is followed until one is found."""
    by_id = {el.get("uniquename"): el for el in spells
             if el.tag in ("activespell", "togglespell") and el.get("uniquename")}
    info: dict[str, SpellInfo] = {}
    for spell_id, el in by_id.items():
        cooldown, stage, seen = float(el.get("recastdelay") or 0), el, {spell_id}
        while cooldown <= 0:
            multi = stage.find(".//multispell")
            stage = by_id.get(multi.get("spell")) if multi is not None else None
            if stage is None or stage.get("uniquename") in seen:
                break
            seen.add(stage.get("uniquename"))
            cooldown = float(stage.get("recastdelay") or 0)
        if cooldown > 0:
            info[spell_id] = SpellInfo(cooldown, el.get("namelocatag") or f"@SPELLS_{spell_id}",
                                       multi_stage=len(seen) > 1)
    return info


def _spell_lists(items: ET.Element) -> dict[str, list[tuple[str, str | None]]]:
    """Item id -> [(spell id, slots)], resolving `reference` inheritance and `removespell`."""
    raw = {el.get("uniquename"): el.find("craftingspelllist") for el in items}  # direct child only
    resolved: dict[str, list[tuple[str, str | None]]] = {}

    def resolve(name: str | None, seen: tuple[str, ...] = ()) -> list[tuple[str, str | None]]:
        if name is None or name in seen or raw.get(name) is None:
            return []
        if name not in resolved:
            spell_list = raw[name]
            spells = list(resolve(spell_list.get("reference"), seen + (name,)))
            removed = {r.get("uniquename") for r in spell_list.findall("removespell")}
            spells = [s for s in spells if s[0] not in removed]
            spells += [(c.get("uniquename"), c.get("slots")) for c in spell_list.findall("craftspell")]
            resolved[name] = spells
        return resolved[name]

    return {name: resolve(name) for name in raw}


def collect(items: ET.Element, spells: dict[str, SpellInfo],
            strings: dict[str, str]) -> tuple[list[GameAbility], list[str]]:
    """In-scope abilities, plus notes about items that had to be skipped."""
    spell_lists, spell_data = _spell_lists(items), spells
    found: list[GameAbility] = []
    skipped: list[str] = []
    for el in items:
        uid = el.get("uniquename", "")
        if not uid.startswith(TIER):
            continue
        slottype, shop = el.get("slottype"), el.get("shopcategory")
        if slottype == "mainhand" and shop == "weapons":
            kind, key = "weapon", "E"
            spells = [s for s, slots in spell_lists.get(uid, []) if slots == WEAPON_E_SLOT]
        elif slottype in ARMOR and shop == ARMOR[slottype][0]:
            kind, key = "armor", ARMOR[slottype][1]
            spells = [s for s, _ in spell_lists.get(uid, [])]
        else:
            continue
        candidates = [s for s in dict.fromkeys(spells) if s in spell_data]  # with a cooldown, no repeats
        if not candidates:
            if kind == "weapon" and spells:
                skipped.append(f"{uid}: no E ability with a cooldown")
            continue
        item_name = strings.get(f"@ITEMS_{uid}")
        if not item_name:
            skipped.append(f"{uid}: no English name")
            continue
        item_name = TIER_PREFIX.sub("", item_name).strip()
        for spell in candidates:
            data = spell_data[spell]
            ability_name = strings.get(data.name_key)
            if not ability_name:
                skipped.append(f"{uid} / {spell}: no English ability name")
                continue
            found.append(GameAbility(item_name, ability_name, key, data.cooldown_s, kind, data.multi_stage))
    return found, skipped


def _split_compound(word: str, is_known: Callable[[str], bool]) -> list[str] | None:
    """Best split into two known words. The split whose shorter part is longest wins, which favours
    real words over fragments: "dawnsong" -> "dawn song", not "dawns ong"."""
    splits = [(word[:cut], word[cut:]) for cut in range(MIN_PART, len(word) - MIN_PART + 1)]
    known_splits = [s for s in splits if is_known(s[0]) and is_known(s[1])]
    if not known_splits:
        return None
    return list(max(known_splits, key=lambda s: min(len(s[0]), len(s[1]))))


def speakable(text: str, is_known: Callable[[str], bool]) -> str:
    """Normalized phrase, with unknown compound words split into known ones ("bloodletter" ->
    "blood letter"). Words that still aren't known are kept; the editor flags them."""
    words: list[str] = []
    for word in normalize_phrase(text).split():
        if word in SPOKEN:
            words.extend(SPOKEN[word].split())
            continue
        if not is_known(word) and word.endswith("'s") and is_known(word[:-2]):
            word = word[:-2]
        parts = None if is_known(word) else _split_compound(word, is_known)
        words.extend(parts or [word])
    return " ".join(words)


def to_abilities(game: Iterable[GameAbility],
                 is_known: Callable[[str], bool]) -> tuple[list[Ability], list[str]]:
    """App abilities with generated phrases: weapon E entries, armor entries per item, then one
    entry per armor ability ("Dodge F") for players who call the effect rather than the item.
    Phrases already taken by an earlier entry are dropped (an entry left with none is skipped);
    every drop is reported."""
    game = list(game)
    say = lambda text: speakable(text, is_known)  # noqa: E731
    # distinct E abilities per weapon name (several item ids can share one display name)
    weapon_e_counts = Counter(item for item, _ in
                              dict.fromkeys((g.item_name, g.ability_name) for g in game if g.kind == "weapon"))
    candidates: list[tuple[str, list[str], str, float, str]] = []  # name, phrases, slot, cooldown, category
    for g in game:
        if g.kind == "weapon" and weapon_e_counts[g.item_name] == 1:
            candidates.append((f"{g.item_name} E", [f"{say(g.item_name)} e", say(g.item_name)],
                               g.slot, g.cooldown_s, "weapon"))
        elif g.kind == "weapon":
            candidates.append((f"{g.item_name} E – {g.ability_name}", [f"{say(g.item_name)} {say(g.ability_name)}"],
                               g.slot, g.cooldown_s, "weapon"))
        else:
            candidates.append((f"{g.item_name} – {g.ability_name} {g.slot}",
                               [f"{say(g.item_name)} {say(g.ability_name)}"], g.slot, g.cooldown_s, "armor_item"))
    shared: dict[tuple[str, str], list[float]] = {}
    for g in game:
        if g.kind == "armor":
            cooldowns = shared.setdefault((g.ability_name, g.slot), [])
            if g.cooldown_s not in cooldowns:
                cooldowns.append(g.cooldown_s)
    for (ability, slot), cooldowns in shared.items():
        for cooldown in cooldowns:
            name = f"{ability} {slot}" if len(cooldowns) == 1 else f"{ability} {slot} ({cooldown:g} s)"
            candidates.append((name, [f"{say(ability)} {slot.lower()}", say(ability)], slot, cooldown,
                               "armor_ability"))

    abilities: list[Ability] = []
    notes: list[str] = []
    owners: dict[str, str] = {}
    ids: set[str] = set()
    for name, phrases, slot, cooldown, category in candidates:
        if not 0 < cooldown <= MAX_COOLDOWN_S:
            notes.append(f"Skipped {name}: cooldown {cooldown:g} s is out of range")
            continue
        kept, dropped = [], []
        for phrase in phrases:
            if phrase.split()[0] == RESERVED_WORD:
                dropped.append(f"{name}: dropped phrase '{phrase}' (starts with '{RESERVED_WORD}')")
            elif phrase in owners:
                dropped.append(f"{name}: dropped phrase '{phrase}' (already used by {owners[phrase]})")
            elif phrase not in kept:
                kept.append(phrase)
        if not kept:
            notes.append(f"Skipped {name}: all its phrases are already used by "
                         f"{', '.join(dict.fromkeys(owners[p] for p in phrases if p in owners))}")
            continue
        notes.extend(dropped)
        entry = Ability(make_id(name, ids), name, slot, cooldown, tuple(kept), category)
        ids.add(entry.id)
        owners.update({p: name for p in kept})
        abilities.append(entry)
    return abilities, notes
