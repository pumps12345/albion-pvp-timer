"""Generate the built-in ability list from Albion Online game data.

Downloads items.xml, spells.xml and localization.json from https://github.com/ao-data/ao-bin-dumps
(pinned to the latest commit, cached under build/ao-bin-dumps/), keeps each weapon's E ability plus
the chest R / helmet D / boots F actives, generates voice phrases, checks them against the Vosk
model's vocabulary, and writes src/pvptimer/data/default_abilities.json and build/import_report.txt.

Usage: .venv/Scripts/python scripts/import_game_data.py [--out PATH]
"""
import argparse
import json
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from functools import lru_cache
from pathlib import Path

from pvptimer import paths
from pvptimer.abilities import ability_file
from pvptimer.gamedata import collect, english_strings, spell_info, to_abilities
from pvptimer.jsonio import atomic_write_json

ROOT = Path(__file__).resolve().parents[1]
REPO = "ao-data/ao-bin-dumps"
FILES = ("items.xml", "spells.xml", "localization.json")
CACHE = ROOT / "build" / "ao-bin-dumps"


def latest_commit() -> str:
    with urllib.request.urlopen(f"https://api.github.com/repos/{REPO}/commits/master") as response:
        return json.load(response)["sha"]


def download(commit: str) -> Path:
    folder = CACHE / commit[:12]
    folder.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = folder / name
        if not target.exists():
            print(f"downloading {name} ...")
            urllib.request.urlretrieve(f"https://raw.githubusercontent.com/{REPO}/{commit}/{name}", target)
    return folder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=paths.data_dir() / "default_abilities.json")
    parser.add_argument("--report", type=Path, default=ROOT / "build" / "import_report.txt")
    args = parser.parse_args()

    commit = latest_commit()
    folder = download(commit)
    strings = english_strings(json.loads((folder / "localization.json").read_text(encoding="utf-8")))
    spells = spell_info(ET.parse(folder / "spells.xml").getroot())
    game, skipped = collect(ET.parse(folder / "items.xml").getroot(), spells, strings)

    import vosk
    vosk.SetLogLevel(-1)
    model = vosk.Model(str(paths.model_dir()))

    @lru_cache(maxsize=None)
    def is_known(word: str) -> bool:
        return model.vosk_model_find_word(word) != -1

    abilities, notes = to_abilities(game, is_known)
    unknown = [(a.name, sorted({w for p in a.phrases for w in p.split() if not is_known(w)}))
               for a in abilities]
    unknown = [(name, words) for name, words in unknown if words]
    recast_stage = sorted({f"{g.item_name} / {g.ability_name}: {g.cooldown_s:g} s" for g in game if g.verify})
    atomic_write_json(args.out, ability_file(abilities))

    counts = Counter(a.slot for a in abilities)
    lines = [
        f"Source: https://github.com/{REPO}/tree/{commit}",
        f"Abilities: {len(abilities)} (E {counts['E']}, R {counts['R']}, D {counts['D']}, F {counts['F']})",
        f"Phrases with words the speech model doesn't know: {len(unknown)} abilities", "",
        "== Unknown words (respell these in the Editor) ==",
        *(f"  {name}: {', '.join(words)}" for name, words in unknown), "",
        "== Cooldown read from a recast stage (check these in game) ==", *(f"  {r}" for r in recast_stage), "",
        "== Phrase clashes ==", *(f"  {n}" for n in notes), "",
        "== Skipped items ==", *(f"  {s}" for s in skipped),
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:3]))
    print(f"Wrote {args.out}\nFull report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
