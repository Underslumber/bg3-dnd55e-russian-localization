#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


DEFAULT_ENGLISH_PATH = "docs/official-localization/english.xml"
DEFAULT_RUSSIAN_PATH = "docs/official-localization/russian.xml"
DEFAULT_OUTPUT_PATH = "glossary/glossary.official.json"


EXACT_TERMS = {
    "AC",
    "HP",
    "Ability",
    "Abilities",
    "Ability Check",
    "Ability Checks",
    "Action",
    "Action Surge",
    "Attack",
    "Attack Roll",
    "Attack Rolls",
    "Bonus Action",
    "Cantrip",
    "Cantrips",
    "Class",
    "Classes",
    "Concentration",
    "Condition",
    "Conditions",
    "Damage",
    "Difficulty Class",
    "Disadvantage",
    "Feat",
    "Feats",
    "Feature",
    "Features",
    "Healing",
    "Hit Point",
    "Hit Points",
    "Initiative",
    "Long Rest",
    "Mastery Properties",
    "Melee Attack",
    "Movement Speed",
    "Opportunity Attack",
    "Opportunity Attacks",
    "Proficiency",
    "Proficiency Bonus",
    "Ranged Attack",
    "Reaction",
    "Saving Throw",
    "Saving Throws",
    "Short Rest",
    "Spell",
    "Spell Save DC",
    "Spell Slot",
    "Spells",
    "Subclass",
    "Subclasses",
    "Temporary Hit Point",
    "Temporary Hit Points",
    "Weapon",
    "Weapon Mastery",
    "Weapons",
    "Armor Class",
    "Armour Class",
}

KEYWORD_TERMS = {
    "acid damage",
    "acrobatics",
    "animal handling",
    "arcana",
    "aasimar",
    "barbarian",
    "bard",
    "battleaxe",
    "blinded",
    "blowgun",
    "bludgeoning damage",
    "charmed",
    "charisma",
    "chill touch",
    "cleric",
    "club",
    "cold damage",
    "constitution",
    "counterspell",
    "cure wounds",
    "dagger",
    "dart",
    "deafened",
    "deception",
    "dexterity",
    "dragonborn",
    "druid",
    "dwarf",
    "eldritch blast",
    "elf",
    "exhaustion",
    "feat",
    "feats",
    "fighter",
    "fire bolt",
    "fire damage",
    "flail",
    "force damage",
    "frightened",
    "githyanki",
    "githzerai",
    "glaive",
    "gnome",
    "grappled",
    "greataxe",
    "greatclub",
    "greatsword",
    "guidance",
    "guiding bolt",
    "halberd",
    "half-elf",
    "half-orc",
    "halfling",
    "hand crossbow",
    "handaxe",
    "haste",
    "healing word",
    "heavy armor",
    "heavy armour",
    "heavy crossbow",
    "history",
    "human",
    "hunter's mark",
    "initiative",
    "insight",
    "intelligence",
    "intimidation",
    "investigation",
    "invisible",
    "javelin",
    "lance",
    "light armor",
    "light armour",
    "light crossbow",
    "light hammer",
    "lightning damage",
    "longbow",
    "longsword",
    "mace",
    "mage armour",
    "maul",
    "medicine",
    "medium armor",
    "medium armour",
    "misty step",
    "monk",
    "morningstar",
    "nature",
    "necrotic damage",
    "net",
    "orc",
    "paladin",
    "paralyzed",
    "perception",
    "performance",
    "persuasion",
    "petrified",
    "piercing damage",
    "pike",
    "poison damage",
    "poisoned",
    "prone",
    "produce flame",
    "psychic damage",
    "quarterstaff",
    "radiant damage",
    "ranger",
    "rapier",
    "ray of frost",
    "religion",
    "restrained",
    "rogue",
    "sacred flame",
    "scimitar",
    "shocking grasp",
    "shield",
    "shortbow",
    "shortsword",
    "sickle",
    "sleight of hand",
    "sling",
    "sorcerer",
    "spear",
    "spell save dc",
    "spirit guardians",
    "spiritual weapon",
    "stealth",
    "strength",
    "stunned",
    "survival",
    "thunder damage",
    "thunderwave",
    "tiefling",
    "true strike",
    "trident",
    "unconscious",
    "war pick",
    "warhammer",
    "warlock",
    "weapon mastery",
    "whip",
    "wisdom",
    "wizard",
}

TITLE_HINT_WORDS = {
    "acid",
    "action",
    "advantage",
    "aid",
    "alarm",
    "arcane",
    "armor",
    "armour",
    "attack",
    "aura",
    "bane",
    "barbarian",
    "bard",
    "blast",
    "blade",
    "bless",
    "bolt",
    "bonus",
    "burst",
    "cantrip",
    "charm",
    "check",
    "cleric",
    "class",
    "condition",
    "counterspell",
    "cure",
    "damage",
    "darkness",
    "druid",
    "eldritch",
    "evocation",
    "feat",
    "feature",
    "fighter",
    "fire",
    "flame",
    "force",
    "frost",
    "guidance",
    "guiding",
    "hammer",
    "hand",
    "haste",
    "heal",
    "healing",
    "hex",
    "hit",
    "hunter",
    "initiative",
    "lightning",
    "longbow",
    "longsword",
    "magic",
    "mage",
    "master",
    "mastery",
    "metamagic",
    "misty",
    "monk",
    "moon",
    "movement",
    "orb",
    "paladin",
    "poison",
    "potion",
    "proficiency",
    "protection",
    "radiant",
    "rage",
    "ranger",
    "rapier",
    "ray",
    "reaction",
    "resistance",
    "rest",
    "restoration",
    "rogue",
    "saving",
    "scimitar",
    "shield",
    "shortbow",
    "shortsword",
    "skill",
    "sleep",
    "slot",
    "smite",
    "sorcerer",
    "spell",
    "spells",
    "speed",
    "spirit",
    "spiritual",
    "stealth",
    "strike",
    "subclass",
    "surge",
    "sword",
    "throw",
    "thunder",
    "touch",
    "true",
    "turn-based",
    "unarmoured",
    "unarmored",
    "warlock",
    "ward",
    "wave",
    "weapon",
    "web",
    "wizard",
    "word",
}

TITLE_NEUTRAL_WORDS = {
    "a",
    "an",
    "add",
    "additional",
    "activate",
    "always",
    "available",
    "bonus",
    "can",
    "charge",
    "charges",
    "choose",
    "current",
    "extra",
    "for",
    "from",
    "in",
    "initiate",
    "main",
    "menu",
    "new",
    "of",
    "off",
    "passive",
    "passives",
    "plus",
    "prepared",
    "quickened",
    "racial",
    "resource",
    "resources",
    "scroll",
    "select",
    "set",
    "shared",
    "slot",
    "slots",
    "surge",
    "toggle",
    "up",
    "vial",
    "with",
    "without",
}

EXACT_UI_TERMS = {
    "Accept",
    "Add",
    "Cancel",
    "Choose Actions",
    "Close",
    "Honour Mode",
    "New Feat Available",
    "Open",
    "Open (locked)",
    "Read",
    "Remove",
    "Replace Spell",
    "Selected:",
    "Select Feat Passives",
    "Turn-Based Mode",
}

BLACKLIST_SUBSTRINGS = {
    "barrel",
    "bench",
    "book ",
    "bookshelf",
    "bottle",
    "box",
    "bucket",
    "candle",
    "chair",
    "chest",
    "crate",
    "cup",
    "find ",
    "go to ",
    "investigate ",
    "journal",
    "kill ",
    "lantern",
    "letter",
    "note",
    "pillow",
    "plate",
    "postcard",
    "property of ",
    "report to ",
    "return to ",
    "sack",
    "shelf",
    "speak to ",
    "table",
    "talk to ",
    "torch",
    "vase",
    "wagon",
}


@dataclass(frozen=True)
class Candidate:
    english: str
    russian: str
    occurrences: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a compact official glossary from original BG3 localization.")
    parser.add_argument("-EnglishPath", "--english-path", default=DEFAULT_ENGLISH_PATH, dest="english_path")
    parser.add_argument("-RussianPath", "--russian-path", default=DEFAULT_RUSSIAN_PATH, dest="russian_path")
    parser.add_argument("-OutputPath", "--output-path", default=DEFAULT_OUTPUT_PATH, dest="output_path")
    return parser.parse_args()


def read_localization_entries(path: Path) -> dict[str, str]:
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Localization XML was not found: '{resolved_path}'.")

    root = ET.fromstring(resolved_path.read_text(encoding="utf-8-sig"))
    if root.tag != "contentList":
        raise ValueError(f"Localization XML does not contain '/contentList': '{resolved_path}'.")

    entries: dict[str, str] = {}
    for node in root.findall("./content"):
        content_uid = str(node.get("contentuid", "")).strip()
        if not content_uid:
            continue
        entries[content_uid] = str(node.text or "").strip()
    return entries


def strip_markup(text: str) -> str:
    visible = re.sub(r"<[^>]+>", " ", text)
    visible = re.sub(r"\[[^\]]+\]", " ", visible)
    return re.sub(r"\s+", " ", visible).strip()


def normalize_key(text: str) -> str:
    normalized = strip_markup(text).lower()
    normalized = normalized.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", normalized).strip()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)?", text)


def has_blacklisted_content(text: str) -> bool:
    lower = text.lower()
    return any(fragment in lower for fragment in BLACKLIST_SUBSTRINGS)


def looks_like_dialogue(text: str) -> bool:
    if "<br>" in text or "\n" in text:
        return True

    visible = strip_markup(text)
    if re.search(r"[.!?…][\"”']?$", visible):
        return True

    lower = f" {visible.lower()} "
    return re.search(r"\b(i|you|we|he|she|they|my|your|our|their|me|us|him|her|them)\b", lower) is not None


def contains_title_hint(text: str) -> bool:
    words = {token.lower() for token in tokenize(text)}
    return any(word in TITLE_HINT_WORDS for word in words)


def title_fallback_allowed(text: str) -> bool:
    words = [token.lower() for token in tokenize(text)]
    if not words:
        return False
    if not any(word in TITLE_HINT_WORDS for word in words):
        return False
    return all(word in TITLE_HINT_WORDS or word in TITLE_NEUTRAL_WORDS for word in words)


def is_mechanics_or_ui_candidate(text: str) -> bool:
    if not text:
        return False

    visible = strip_markup(text)
    if not visible or len(visible) > 80:
        return False
    if has_blacklisted_content(visible):
        return False
    if looks_like_dialogue(text):
        return False
    if ("*" in visible or "'" in visible or '"' in visible) and visible not in EXACT_TERMS and visible not in EXACT_UI_TERMS:
        return False

    if visible in EXACT_UI_TERMS or visible in EXACT_TERMS:
        return True

    visible_lower = visible.lower()
    if visible_lower in KEYWORD_TERMS:
        return True

    if text.startswith("<LSTag Tooltip=") and len(tokenize(visible)) <= 6:
        return True

    words = tokenize(visible)
    if ":" in visible and len(words) <= 8:
        colon_hints = ("action", "attack", "damage", "condition", "spell", "class", "feat", "mastery", "saving throw", "weapon", "armor", "armour", "level ")
        if any(hint in visible_lower for hint in colon_hints):
            return True

    if 1 <= len(words) <= 6 and visible == visible.title() and title_fallback_allowed(visible):
        return True

    return False


def candidate_priority(candidate: Candidate) -> tuple[int, int, int, int, str, str]:
    english_visible = strip_markup(candidate.english)
    russian_visible = strip_markup(candidate.russian)
    english_words = tokenize(english_visible)

    return (
        candidate.occurrences,
        1 if "<" not in candidate.english and "[" not in candidate.english else 0,
        1 if english_visible == english_visible.title() else 0,
        -len(english_words),
        english_visible.lower(),
        russian_visible.lower(),
    )


def choose_canonical_candidate(candidates: list[Candidate]) -> Candidate:
    return max(candidates, key=candidate_priority)


def build_glossary(english_entries: dict[str, str], russian_entries: dict[str, str]) -> dict[str, str]:
    grouped: dict[str, dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))

    for content_uid, english_text in english_entries.items():
        russian_text = russian_entries.get(content_uid, "").strip()
        if not english_text or not russian_text:
            continue
        if not is_mechanics_or_ui_candidate(english_text):
            continue

        normalized_key = normalize_key(english_text)
        if not normalized_key:
            continue

        grouped[normalized_key][(english_text, russian_text)] += 1

    glossary: dict[str, str] = {}
    for variants in grouped.values():
        candidates = [
            Candidate(english=english, russian=russian, occurrences=count)
            for (english, russian), count in variants.items()
        ]
        chosen = choose_canonical_candidate(candidates)
        glossary[chosen.english] = chosen.russian

    return dict(sorted(glossary.items(), key=lambda item: (item[0].lower(), item[0])))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()

    try:
        english_path = Path(args.english_path).resolve()
        russian_path = Path(args.russian_path).resolve()
        output_path = Path(args.output_path).resolve()

        english_entries = read_localization_entries(english_path)
        russian_entries = read_localization_entries(russian_path)
        glossary = build_glossary(english_entries=english_entries, russian_entries=russian_entries)
        write_json(output_path, glossary)
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    print(
        "[build-official-glossary.py] "
        f"Official glossary written to '{output_path}'. Entries={len(glossary)}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
