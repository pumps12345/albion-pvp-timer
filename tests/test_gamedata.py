import xml.etree.ElementTree as ET

import pytest

from pvptimer.abilities import validate
from pvptimer.gamedata import (GameAbility, SpellInfo, collect, english_strings, speakable, spell_info,
                               to_abilities)

ITEMS = ET.fromstring("""
<items>
  <weapon uniquename="T4_MAIN_DAGGER" slottype="mainhand" shopcategory="weapons">
    <craftingspelllist>
      <craftspell uniquename="QSTAB" slots="1" />
      <craftspell uniquename="BLOODTHIRSTYBLADE" slots="3" tag="A" />
      <craftspell uniquename="PASSIVE_BLEED" />
    </craftingspelllist>
    <enchantments><enchantment enchantmentlevel="1">
      <craftingspelllist><craftspell uniquename="IGNORED_ENCHANT_SPELL" slots="3" /></craftingspelllist>
    </enchantment></enchantments>
  </weapon>
  <weapon uniquename="T5_MAIN_DAGGER" slottype="mainhand" shopcategory="weapons">
    <craftingspelllist reference="T4_MAIN_DAGGER" />
  </weapon>
  <weapon uniquename="T4_MAIN_RAPIER_MORGANA" slottype="mainhand" shopcategory="weapons">
    <craftingspelllist reference="T4_MAIN_DAGGER">
      <removespell uniquename="BLOODTHIRSTYBLADE" />
      <craftspell uniquename="RAPIERSTAB" slots="3" tag="A" />
    </craftingspelllist>
  </weapon>
  <weapon uniquename="T4_2H_TOOL_PICK" slottype="mainhand" shopcategory="gathering">
    <craftingspelllist><craftspell uniquename="RAPIERSTAB" slots="3" /></craftingspelllist>
  </weapon>
  <equipmentitem uniquename="T4_HEAD_LEATHER_SET2" slottype="head" shopcategory="head">
    <craftingspelllist>
      <craftspell uniquename="ENERGY_BARRIER" />
      <craftspell uniquename="RETALIATE2" />
      <craftspell uniquename="PASSIVE_BALANCE" />
    </craftingspelllist>
  </equipmentitem>
  <equipmentitem uniquename="T4_ARMOR_CLOTH_SET1" slottype="armor" shopcategory="armors">
    <craftingspelllist><craftspell uniquename="HEAL_SELF" /></craftingspelllist>
  </equipmentitem>
  <equipmentitem uniquename="T4_SHOES_LEATHER_NONAME" slottype="shoes" shopcategory="shoes">
    <craftingspelllist><craftspell uniquename="HEAL_SELF" /></craftingspelllist>
  </equipmentitem>
  <weapon uniquename="T4_2H_DIVINESTAFF" slottype="mainhand" shopcategory="weapons">
    <craftingspelllist><craftspell uniquename="HOLYSHIELD" slots="3" /></craftingspelllist>
  </weapon>
  <weapon uniquename="T4_MAIN_FIRESTAFF" slottype="mainhand" shopcategory="weapons">
    <craftingspelllist><craftspell uniquename="PYROBLAST_SKILLSHOT" slots="3" /></craftingspelllist>
  </weapon>
  <weapon uniquename="T4_MAIN_SWORD_CRYSTAL" slottype="mainhand" shopcategory="weapons">
    <craftingspelllist><craftspell uniquename="NO_COOLDOWN_ANYWHERE" slots="3" /></craftingspelllist>
  </weapon>
  <equipmentitem uniquename="T4_OFF_SHIELD" slottype="offhand" shopcategory="offhands">
    <craftingspelllist><craftspell uniquename="HEAL_SELF" /></craftingspelllist>
  </equipmentitem>
</items>
""")

SPELLS = ET.fromstring("""
<spells>
  <activespell uniquename="QSTAB" recastdelay="3" />
  <togglespell uniquename="BLOODTHIRSTYBLADE" recastdelay="20" />
  <activespell uniquename="HOLYSHIELD" recastdelay="0"><multispell spell="HOLYSHIELD_MULTI" timeoutcooldown="21" /></activespell>
  <activespell uniquename="HOLYSHIELD_MULTI" recastdelay="0"><multispell spell="HOLYSHIELD_MULTI2" /></activespell>
  <activespell uniquename="HOLYSHIELD_MULTI2" recastdelay="25" />
  <activespell uniquename="PYROBLAST_SKILLSHOT" recastdelay="15" namelocatag="@SPELLS_PYROBLAST2" />
  <activespell uniquename="NO_COOLDOWN_ANYWHERE" recastdelay="0" />
  <activespell uniquename="RAPIERSTAB" recastdelay="35" />
  <activespell uniquename="ENERGY_BARRIER" recastdelay="25" />
  <activespell uniquename="RETALIATE2" recastdelay="45" />
  <activespell uniquename="HEAL_SELF" recastdelay="30" />
  <activespell uniquename="TOGGLE_THING" recastdelay="0" />
  <passivespell uniquename="PASSIVE_BALANCE" />
</spells>
""")

LOCALIZATION = {"tmx": {"body": {"tu": [
    {"@tuid": "@ITEMS_T4_MAIN_DAGGER", "tuv": [{"@xml:lang": "EN-US", "seg": "Adept's Dagger"},
                                                {"@xml:lang": "DE-DE", "seg": "Dolch des Adepten"}]},
    {"@tuid": "@ITEMS_T4_MAIN_RAPIER_MORGANA", "tuv": {"@xml:lang": "EN-US", "seg": "Adept's Bloodletter"}},
    {"@tuid": "@ITEMS_T4_HEAD_LEATHER_SET2", "tuv": [{"@xml:lang": "EN-US", "seg": "Adept's Hunter Hood"}]},
    {"@tuid": "@ITEMS_T4_ARMOR_CLOTH_SET1", "tuv": [{"@xml:lang": "EN-US", "seg": "Adept's Scholar Robe"}]},
    {"@tuid": "@SPELLS_BLOODTHIRSTYBLADE", "tuv": [{"@xml:lang": "EN-US", "seg": "Bloodthirsty Blade"}]},
    {"@tuid": "@SPELLS_RAPIERSTAB", "tuv": [{"@xml:lang": "EN-US", "seg": "Lunging Stabs"}]},
    {"@tuid": "@SPELLS_ENERGY_BARRIER", "tuv": [{"@xml:lang": "EN-US", "seg": "Energy Shield"}]},
    {"@tuid": "@SPELLS_RETALIATE2", "tuv": [{"@xml:lang": "EN-US", "seg": "Retaliate"}]},
    {"@tuid": "@SPELLS_HEAL_SELF", "tuv": [{"@xml:lang": "EN-US", "seg": "Mend"}]},
    {"@tuid": "@ITEMS_T4_2H_DIVINESTAFF", "tuv": [{"@xml:lang": "EN-US", "seg": "Adept's Divine Staff"}]},
    {"@tuid": "@SPELLS_HOLYSHIELD", "tuv": [{"@xml:lang": "EN-US", "seg": "Divine Protection"}]},
    {"@tuid": "@ITEMS_T4_MAIN_FIRESTAFF", "tuv": [{"@xml:lang": "EN-US", "seg": "Adept's Fire Staff"}]},
    {"@tuid": "@SPELLS_PYROBLAST2", "tuv": [{"@xml:lang": "EN-US", "seg": "Fireball"}]},
    {"@tuid": "@ITEMS_T4_MAIN_SWORD_CRYSTAL", "tuv": [{"@xml:lang": "EN-US", "seg": "Adept's Infinity Blade"}]},
    {"@tuid": "@UNRELATED_NO_TUV"},
]}}}

VOCAB = {"blood", "letter", "e", "hunter", "hood", "retaliate", "energy", "shield", "scholar",
         "robe", "mend", "dagger", "let", "ter", "dawn", "dawns", "song", "ong"}
known = VOCAB.__contains__


@pytest.fixture
def game():
    strings = english_strings(LOCALIZATION)
    return collect(ITEMS, spell_info(SPELLS), strings)


def test_english_strings_reads_only_english():
    strings = english_strings(LOCALIZATION)
    assert strings["@ITEMS_T4_MAIN_DAGGER"] == "Adept's Dagger"
    assert strings["@ITEMS_T4_MAIN_RAPIER_MORGANA"] == "Adept's Bloodletter"


def test_spell_info_reads_cooldowns_names_and_follows_recast_stages():
    info = spell_info(SPELLS)
    assert info["RAPIERSTAB"] == SpellInfo(35.0, "@SPELLS_RAPIERSTAB")
    assert info["BLOODTHIRSTYBLADE"].cooldown_s == 20.0                  # toggle abilities count
    assert info["PYROBLAST_SKILLSHOT"].name_key == "@SPELLS_PYROBLAST2"  # explicit name key wins
    assert info["HOLYSHIELD"] == SpellInfo(25.0, "@SPELLS_HOLYSHIELD", multi_stage=True)
    for missing in ("TOGGLE_THING", "PASSIVE_BALANCE", "NO_COOLDOWN_ANYWHERE"):
        assert missing not in info


def test_collect_finds_weapon_e_and_armor_actives(game):
    abilities, skipped = game
    assert abilities == [
        GameAbility("Dagger", "Bloodthirsty Blade", "E", 20.0, "weapon"),
        GameAbility("Bloodletter", "Lunging Stabs", "E", 35.0, "weapon"),     # reference resolved
        GameAbility("Hunter Hood", "Energy Shield", "D", 25.0, "armor"),
        GameAbility("Hunter Hood", "Retaliate", "D", 45.0, "armor"),
        GameAbility("Scholar Robe", "Mend", "R", 30.0, "armor"),
        GameAbility("Divine Staff", "Divine Protection", "E", 25.0, "weapon", verify=True),
        GameAbility("Fire Staff", "Fireball", "E", 15.0, "weapon"),
    ]
    # T5 duplicates, gathering tools and offhands are out of scope; problems are reported
    assert skipped == ["T4_SHOES_LEATHER_NONAME: no English name",
                       "T4_MAIN_SWORD_CRYSTAL: no E ability with a cooldown"]


@pytest.mark.parametrize("text, spoken", [
    ("Bloodletter", "blood letter"),        # compound split into known words
    ("Dawnsong", "dawn song"),              # balanced split beats "dawns ong"
    ("Hunter Hood", "hunter hood"),
    ("Galatine Pair", "gala teen pair"),    # hand-picked sound-alike for a word the model lacks
    ("Rotcaller Staff", "rot caller staff"), # override beats a junk split ("rotc aller")
    ("Shadowkin Pair", "shadowkin pair"),   # unknown and unsplittable: kept, flagged later
])
def test_speakable(text, spoken):
    assert speakable(text, known) == spoken


def test_to_abilities_builds_valid_entries_with_phrases(game):
    abilities, notes = to_abilities(game[0], known)
    by_name = {a.name: a for a in abilities}
    assert by_name["Bloodletter E"].phrases == ("blood letter e", "blood letter")
    assert by_name["Bloodletter E"].cooldown_s == 35.0
    assert by_name["Hunter Hood – Retaliate D"].phrases == ("hunter hood retaliate",)
    assert by_name["Hunter Hood – Retaliate D"].slot == "D"
    assert by_name["Scholar Robe – Mend R"].slot == "R"
    assert notes == []
    for i, a in enumerate(abilities):
        assert validate(a, abilities[:i]) == []


def test_clashing_phrases_are_dropped_and_reported():
    game = [GameAbility("Dagger", "Stab", "E", 10.0, "weapon"),
            GameAbility("Dagger", "Stab", "E", 10.0, "weapon")]   # e.g. two items with one display name
    abilities, notes = to_abilities(game, known)
    assert len(abilities) == 1
    assert notes == ["Skipped Dagger E: all its phrases are already used by Dagger E"]


def test_weapon_with_two_e_options_names_each_by_ability():
    game = [GameAbility("Dagger", "Stab", "E", 10.0, "weapon"),
            GameAbility("Dagger", "Mend", "E", 12.0, "weapon")]
    names = [a.name for a in to_abilities(game, known)[0]]
    assert names == ["Dagger E – Stab", "Dagger E – Mend"]
