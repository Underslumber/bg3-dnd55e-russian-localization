#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


LSTAG_PATTERN = re.compile(
    r'<LSTag\b(?P<attributes>[^>]*)>(?P<label>.*?)</LSTag>',
    re.IGNORECASE | re.DOTALL,
)
ATTRIBUTE_PATTERN = re.compile(r'(\w+)="([^"]*)"')
MARKUP_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")

# These tooltips describe a precise rules concept. A translated label that does
# not contain the corresponding Russian root almost certainly kept the LSTag in
# the English word position after the surrounding words were reordered.
TOOLTIP_LABEL_ROOTS: dict[str, tuple[str, ...]] = {
    "Abilities": ("характерист",),
    "Ability": ("характерист",),
    "AbilityCheck": ("провер",),
    "AbilityModifier": ("модификатор",),
    "AttackRoll": ("атак",),
    "Charisma": ("харизм",),
    "Constitution": ("вынослив",),
    "Dexterity": ("ловкост",),
    "DifficultyClass": ("кс", "сл"),
    "Intelligence": ("интеллект",),
    "SavingThrow": ("испытан",),
    "Strength": ("сил",),
    "Wisdom": ("мудрост",),
}

TOOLTIP_CANONICAL_LABELS: dict[str, tuple[re.Pattern[str], str]] = {
    "ArmourClass": (
        re.compile(r"(?:\bкб\b|класс\w*\s+брони|классу\s+брони)", re.IGNORECASE),
        "КБ / класс брони",
    ),
    "DifficultyClass": (re.compile(r"\bкс\b", re.IGNORECASE), "КС"),
    "HitPoints": (re.compile(r"\bоз\b", re.IGNORECASE), "ОЗ"),
    "OpportunityAttack": (
        re.compile(r"внеочередн", re.IGNORECASE),
        "внеочередная атака",
    ),
    "TemporaryHitPoints": (
        re.compile(r"временн\w*\s+оз\b", re.IGNORECASE),
        "временные ОЗ",
    ),
}

NAMED_REFERENCE_TYPES = {"Passive", "Spell", "Status"}
REFERENCE_TARGET_TYPES = NAMED_REFERENCE_TYPES | {"Skills"}
STAT_TYPE_TO_TOOLTIP_TYPE = {
    "PassiveData": "Passive",
    "SpellData": "Spell",
    "StatusData": "Status",
}
SKILL_TOOLTIP_IDS = {
    "Acrobatics",
    "AnimalHandling",
    "Arcana",
    "Athletics",
    "Deception",
    "History",
    "Insight",
    "Intimidation",
    "Investigation",
    "Medicine",
    "Nature",
    "Perception",
    "Performance",
    "Persuasion",
    "Religion",
    "SleightOfHand",
    "Stealth",
    "Survival",
}
SKILL_REFERENCE_TERMS: dict[str, tuple[str, re.Pattern[str]]] = {
    "Acrobatics": ("Acrobatics", re.compile(r"акробатик\w*", re.IGNORECASE)),
    "AnimalHandling": (
        "Animal Handling",
        re.compile(r"(?:дрессировк\w*|уход\w* за животн\w*)", re.IGNORECASE),
    ),
    "Arcana": ("Arcana", re.compile(r"маги\w*", re.IGNORECASE)),
    "Athletics": ("Athletics", re.compile(r"атлетик\w*", re.IGNORECASE)),
    "Deception": ("Deception", re.compile(r"обман\w*", re.IGNORECASE)),
    "History": ("History", re.compile(r"истори\w*", re.IGNORECASE)),
    "Insight": (
        "Insight",
        re.compile(r"проницательност\w*", re.IGNORECASE),
    ),
    "Intimidation": (
        "Intimidation",
        re.compile(r"запугивани\w*", re.IGNORECASE),
    ),
    "Investigation": (
        "Investigation",
        re.compile(r"расследовани\w*", re.IGNORECASE),
    ),
    "Medicine": ("Medicine", re.compile(r"медицин\w*", re.IGNORECASE)),
    "Nature": ("Nature", re.compile(r"природ\w*", re.IGNORECASE)),
    "Perception": (
        "Perception",
        re.compile(
            r"(?:внимани\w*|восприяти\w*|внимательност\w*)",
            re.IGNORECASE,
        ),
    ),
    "Performance": (
        "Performance",
        re.compile(r"исполнени\w*", re.IGNORECASE),
    ),
    "Persuasion": (
        "Persuasion",
        re.compile(r"убеждени\w*", re.IGNORECASE),
    ),
    "Religion": ("Religion", re.compile(r"религи\w*", re.IGNORECASE)),
    "SleightOfHand": (
        "Sleight of Hand",
        re.compile(r"ловкост\w* рук", re.IGNORECASE),
    ),
    "Stealth": ("Stealth", re.compile(r"скрытност\w*", re.IGNORECASE)),
    "Survival": ("Survival", re.compile(r"выживани\w*", re.IGNORECASE)),
}
ENGLISH_SKILL_CONTEXT_PATTERN = re.compile(
    r"\b(?:skill|skills|check|checks|proficien\w*|expertise)\b",
    re.IGNORECASE,
)
RUSSIAN_SKILL_CONTEXT_PATTERN = re.compile(
    r"\b(?:навык\w*|проверк\w*|владени\w*|экспертност\w*)\b",
    re.IGNORECASE,
)
SKILL_CONTEXT_MAX_DISTANCE = 120
LOCALIZATION_HANDLE_PATTERN = re.compile(r"^(h[a-f0-9g]+);\d+$", re.IGNORECASE)


@dataclass(frozen=True)
class TooltipTag:
    type: str
    tooltip: str
    label: str

    @property
    def target(self) -> tuple[str, str]:
        return self.type, self.tooltip


@dataclass(frozen=True)
class SourceEntity:
    type: str
    name: str
    display_uid: str
    display_name: str
    description_uid: str
    source_file: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit BG3 LSTag tooltip preservation, Russian label binding, and "
            "possible unlinked named references."
        )
    )
    parser.add_argument(
        "-EnglishPath",
        "--english-path",
        default=".cache/upstream/english.xml",
        dest="english_path",
    )
    parser.add_argument(
        "-RussianPath",
        "--russian-path",
        default="Mods/DnD 5.5e AIO Russian/Localization/Russian/russian.xml",
        dest="russian_path",
    )
    parser.add_argument(
        "-OutputPath",
        "--output-path",
        default="build/tooltip-link-audit.json",
        dest="output_path",
    )
    parser.add_argument(
        "-ReviewerInputPath",
        "--reviewer-input-path",
        default="build/tooltip-binding-review-input.json",
        dest="reviewer_input_path",
    )
    parser.add_argument(
        "-StatsPath",
        "--stats-path",
        default="",
        dest="stats_path",
        help=(
            "Optional parent-mod Stats/Generated/Data directory. When supplied, "
            "the audit resolves real Spell/Passive/Status/Skills IDs and searches "
            "descriptions owned by all stat categories, including items and "
            "interrupts, for unlinked references."
        ),
    )
    parser.add_argument(
        "-RootTemplatesPath",
        "--root-templates-path",
        default="",
        dest="root_templates_path",
        help=(
            "Optional directory containing RootTemplates converted to LSX. "
            "Their item descriptions are included as reference owners."
        ),
    )
    return parser.parse_args()


def normalize_text(value: str) -> str:
    visible = MARKUP_PATTERN.sub("", str(value or ""))
    return WHITESPACE_PATTERN.sub(" ", visible).strip()


def normalize_reference_label(value: str) -> str:
    return normalize_text(value).strip(' «»".,:;!?()[]').casefold()


def read_localization(path: Path) -> dict[str, dict[str, str]]:
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Localization XML was not found: '{resolved}'.")

    root = ET.fromstring(resolved.read_text(encoding="utf-8-sig"))
    if root.tag != "contentList":
        raise ValueError(f"Expected contentList root in '{resolved}'.")

    entries: dict[str, dict[str, str]] = {}
    for node in root.findall("./content"):
        content_uid = str(node.get("contentuid", "")).strip()
        if not content_uid:
            raise ValueError(f"Empty contentuid in '{resolved}'.")
        if content_uid in entries:
            raise ValueError(f"Duplicate contentuid '{content_uid}' in '{resolved}'.")
        entries[content_uid] = {
            "version": str(node.get("version", "") or ""),
            "text": str(node.text or ""),
        }
    return entries


def extract_tooltip_tags(text: str) -> list[TooltipTag]:
    tags: list[TooltipTag] = []
    for match in LSTAG_PATTERN.finditer(str(text or "")):
        attributes = dict(ATTRIBUTE_PATTERN.findall(match.group("attributes")))
        tooltip = str(attributes.get("Tooltip", "")).strip()
        if not tooltip:
            continue
        tags.append(
            TooltipTag(
                type=str(attributes.get("Type", "")).strip(),
                tooltip=tooltip,
                label=normalize_text(match.group("label")),
            )
        )
    return tags


def subtract_counter(
    left: Counter[tuple[str, str]], right: Counter[tuple[str, str]]
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for (tag_type, tooltip), count in sorted((left - right).items()):
        result.append({"type": tag_type, "tooltip": tooltip, "count": count})
    return result


def audit_preservation(
    english_entries: dict[str, dict[str, str]],
    russian_entries: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    for content_uid in sorted(english_entries.keys() & russian_entries.keys()):
        english_tags = extract_tooltip_tags(english_entries[content_uid]["text"])
        russian_tags = extract_tooltip_tags(russian_entries[content_uid]["text"])
        english_targets = Counter(tag.target for tag in english_tags)
        russian_targets = Counter(tag.target for tag in russian_tags)
        if english_targets == russian_targets:
            continue
        issues.append(
            {
                "contentuid": content_uid,
                "version": russian_entries[content_uid]["version"],
                "missingFromRussian": subtract_counter(english_targets, russian_targets),
                "extraInRussian": subtract_counter(russian_targets, english_targets),
                "englishText": english_entries[content_uid]["text"],
                "russianText": russian_entries[content_uid]["text"],
            }
        )
    return issues


def audit_russian_binding(
    russian_entries: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for content_uid, entry in sorted(russian_entries.items()):
        for tag in extract_tooltip_tags(entry["text"]):
            expected_roots = TOOLTIP_LABEL_ROOTS.get(tag.tooltip)
            if not expected_roots:
                continue
            normalized_label = tag.label.casefold().replace("ё", "е")
            if any(root in normalized_label for root in expected_roots):
                continue
            issues.append(
                {
                    "contentuid": content_uid,
                    "version": entry["version"],
                    "type": tag.type,
                    "tooltip": tag.tooltip,
                    "label": tag.label,
                    "expectedRussianRoots": ", ".join(expected_roots),
                    "russianText": entry["text"],
                }
            )
    return issues


def audit_tooltip_terminology(
    russian_entries: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for content_uid, entry in sorted(russian_entries.items()):
        for tag in extract_tooltip_tags(entry["text"]):
            rule = TOOLTIP_CANONICAL_LABELS.get(tag.tooltip)
            if rule is None:
                continue
            pattern, preferred = rule
            if pattern.search(tag.label):
                continue
            issues.append(
                {
                    "contentuid": content_uid,
                    "version": entry["version"],
                    "tooltip": tag.tooltip,
                    "label": tag.label,
                    "preferredTerm": preferred,
                    "russianText": entry["text"],
                }
            )
    return issues


def audit_cross_language_terminology(
    english_entries: dict[str, dict[str, str]],
    russian_entries: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    for content_uid in sorted(english_entries.keys() & russian_entries.keys()):
        english_text = normalize_text(english_entries[content_uid]["text"])
        if not re.search(r"\bPerception\b", english_text, re.IGNORECASE):
            continue
        russian_text = normalize_text(russian_entries[content_uid]["text"])
        match = re.search(r"\b(?:восприяти\w*|внимательност\w*)\b", russian_text, re.IGNORECASE)
        if match is None:
            continue
        issues.append(
            {
                "contentuid": content_uid,
                "version": russian_entries[content_uid]["version"],
                "englishTerm": "Perception",
                "foundTerm": match.group(0),
                "preferredTerm": "Внимание",
                "englishText": english_entries[content_uid]["text"],
                "russianText": russian_entries[content_uid]["text"],
            }
        )
    return issues


def audit_skill_references(
    english_entries: dict[str, dict[str, str]],
    russian_entries: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for content_uid in sorted(english_entries.keys() & russian_entries.keys()):
        english_text = normalize_text(english_entries[content_uid]["text"])
        english_context_matches = list(
            ENGLISH_SKILL_CONTEXT_PATTERN.finditer(english_text)
        )
        if not english_context_matches:
            continue
        russian_entry = russian_entries[content_uid]
        russian_text = normalize_text(russian_entry["text"])
        existing_targets = {
            tag.tooltip
            for tag in extract_tooltip_tags(russian_entry["text"])
            if tag.type == "Skills"
        }
        for tooltip, (english_term, russian_pattern) in SKILL_REFERENCE_TERMS.items():
            if tooltip in existing_targets:
                continue
            english_pattern = re.compile(
                rf"(?<![A-Za-z]){re.escape(english_term)}(?![A-Za-z])",
                re.IGNORECASE,
            )
            english_skill_matches = list(english_pattern.finditer(english_text))
            if not english_skill_matches:
                continue
            english_distance = min(
                abs(skill_match.start() - context_match.end())
                if skill_match.start() >= context_match.end()
                else abs(context_match.start() - skill_match.end())
                for skill_match in english_skill_matches
                for context_match in english_context_matches
            )
            if english_distance > SKILL_CONTEXT_MAX_DISTANCE:
                continue
            russian_matches = list(russian_pattern.finditer(russian_text))
            if not russian_matches:
                continue
            russian_context_matches = list(
                RUSSIAN_SKILL_CONTEXT_PATTERN.finditer(russian_text)
            )
            russian_match = min(
                russian_matches,
                key=lambda skill_match: (
                    not skill_match.group(0)[:1].isupper(),
                    min(
                        (
                            abs(skill_match.start() - context_match.end())
                            if skill_match.start() >= context_match.end()
                            else abs(context_match.start() - skill_match.end())
                        )
                        for context_match in russian_context_matches
                    )
                    if russian_context_matches
                    else skill_match.start(),
                ),
            )
            findings.append(
                {
                    "contentuid": content_uid,
                    "version": russian_entry["version"],
                    "label": russian_match.group(0),
                    "suggestedType": "Skills",
                    "suggestedTooltip": tooltip,
                    "englishTerm": english_term,
                    "englishText": english_entries[content_uid]["text"],
                    "russianText": russian_entry["text"],
                }
            )
    return findings


def build_named_reference_lexicon(
    entries: dict[str, dict[str, str]],
) -> dict[str, tuple[TooltipTag, str, int]]:
    candidates: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    source_uids: dict[tuple[str, str, str], str] = {}
    for content_uid, entry in entries.items():
        for tag in extract_tooltip_tags(entry["text"]):
            if tag.type not in NAMED_REFERENCE_TYPES:
                continue
            label = normalize_reference_label(tag.label)
            if len(label) < 5:
                continue
            candidates[label][tag.target] += 1
            source_uids.setdefault((label, *tag.target), content_uid)

    lexicon: dict[str, tuple[TooltipTag, str, int]] = {}
    for label, targets in candidates.items():
        if len(targets) != 1:
            continue
        (tag_type, tooltip), evidence_count = targets.most_common(1)[0]
        lexicon[label] = (
            TooltipTag(type=tag_type, tooltip=tooltip, label=label),
            source_uids[(label, tag_type, tooltip)],
            evidence_count,
        )
    return lexicon


def compile_reference_pattern(label: str) -> re.Pattern[str]:
    return re.compile(
        rf"(?<![0-9A-Za-zА-Яа-яЁё]){re.escape(label)}(?![0-9A-Za-zА-Яа-яЁё])",
        re.IGNORECASE,
    )


def audit_unlinked_named_references(
    russian_entries: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    lexicon = build_named_reference_lexicon(russian_entries)
    patterns = {label: compile_reference_pattern(label) for label in lexicon}
    findings: list[dict[str, object]] = []

    for content_uid, entry in sorted(russian_entries.items()):
        unlinked_text = LSTAG_PATTERN.sub(" ", entry["text"])
        normalized_unlinked_text = WHITESPACE_PATTERN.sub(" ", unlinked_text).casefold()
        for label, pattern in patterns.items():
            if not pattern.search(normalized_unlinked_text):
                continue
            tag, source_uid, evidence_count = lexicon[label]
            findings.append(
                {
                    "contentuid": content_uid,
                    "version": entry["version"],
                    "label": label,
                    "suggestedType": tag.type,
                    "suggestedTooltip": tag.tooltip,
                    "evidenceContentuid": source_uid,
                    "evidenceCount": evidence_count,
                    "russianText": entry["text"],
                }
            )
    return findings


def parse_localization_handle(value: str) -> str:
    match = LOCALIZATION_HANDLE_PATTERN.fullmatch(str(value or "").strip())
    return match.group(1) if match else ""


def read_stat_entries(stats_path: Path) -> dict[str, dict[str, object]]:
    resolved = stats_path.resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(f"Stats directory was not found: '{resolved}'.")

    entries: dict[str, dict[str, object]] = {}
    for source_path in sorted(resolved.rglob("*.txt")):
        text = source_path.read_text(encoding="utf-8-sig", errors="replace")
        parts = re.split(r'(?m)^new entry "([^"]+)"\s*$', text)
        for index in range(1, len(parts), 2):
            name = parts[index]
            body = parts[index + 1]
            type_match = re.search(r'(?m)^type "([^"]+)"', body)
            using_match = re.search(r'(?m)^using "([^"]+)"', body)
            entries[name] = {
                "type": type_match.group(1) if type_match else "",
                "using": using_match.group(1) if using_match else "",
                "data": dict(re.findall(r'(?m)^data "([^"]+)" "([^"]*)"', body)),
                "source_file": str(source_path),
            }
    return entries


def resolve_stat_data(
    entries: dict[str, dict[str, object]],
    entry_name: str,
    key: str,
    visited: set[str] | None = None,
) -> str:
    entry = entries.get(entry_name)
    if entry is None:
        return ""
    visited = set() if visited is None else visited
    if entry_name in visited:
        return ""
    visited.add(entry_name)

    data = entry["data"]
    assert isinstance(data, dict)
    if key in data:
        return str(data[key])
    parent = str(entry["using"] or "")
    return resolve_stat_data(entries, parent, key, visited) if parent else ""


def build_source_entities(
    *,
    stats_path: Path,
    russian_entries: dict[str, dict[str, str]],
) -> list[SourceEntity]:
    stat_entries = read_stat_entries(stats_path)
    entities: list[SourceEntity] = []
    for name, entry in stat_entries.items():
        stat_type = str(entry["type"] or "")
        tooltip_type = STAT_TYPE_TO_TOOLTIP_TYPE.get(stat_type, stat_type or "Unknown")
        if name in SKILL_TOOLTIP_IDS:
            tooltip_type = "Skills"
        display_uid = parse_localization_handle(
            resolve_stat_data(stat_entries, name, "DisplayName")
        )
        display_name = (
            normalize_text(russian_entries[display_uid]["text"])
            if display_uid in russian_entries
            else ""
        )
        if not (4 <= len(display_name) <= 80):
            display_name = ""
        description_uid = parse_localization_handle(
            resolve_stat_data(stat_entries, name, "Description")
        )
        if not display_name and description_uid not in russian_entries:
            continue
        entities.append(
            SourceEntity(
                type=tooltip_type,
                name=name,
                display_uid=display_uid,
                display_name=display_name,
                description_uid=description_uid,
                source_file=str(entry["source_file"]),
            )
        )
    return entities


def build_root_template_entities(
    *,
    root_templates_path: Path,
    russian_entries: dict[str, dict[str, str]],
) -> list[SourceEntity]:
    resolved = root_templates_path.resolve()
    if not resolved.is_dir():
        raise FileNotFoundError(
            f"RootTemplates LSX directory was not found: '{resolved}'."
        )

    entities: list[SourceEntity] = []
    for source_path in sorted(resolved.rglob("*.lsx")):
        root = ET.fromstring(source_path.read_text(encoding="utf-8-sig"))
        for node in root.findall(".//node[@id='GameObjects']"):
            attributes = {
                str(attribute.get("id", "")): attribute
                for attribute in node.findall("./attribute")
            }
            name = str(attributes.get("Name", {}).get("value", ""))
            if not name:
                name = str(attributes.get("MapKey", {}).get("value", ""))
            display_uid = str(attributes.get("DisplayName", {}).get("handle", ""))
            description_uid = str(
                attributes.get("Description", {}).get("handle", "")
            )
            if description_uid not in russian_entries:
                continue
            display_name = (
                normalize_text(russian_entries[display_uid]["text"])
                if display_uid in russian_entries
                else ""
            )
            entities.append(
                SourceEntity(
                    type="ItemTemplate",
                    name=name or source_path.stem,
                    display_uid=display_uid,
                    display_name=display_name,
                    description_uid=description_uid,
                    source_file=str(source_path),
                )
            )
    return entities


def audit_source_catalog_references(
    *,
    entities: list[SourceEntity],
    russian_entries: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    labels: dict[str, Counter[tuple[str, str]]] = defaultdict(Counter)
    evidence: dict[tuple[str, str, str], SourceEntity] = {}
    owners: dict[str, list[SourceEntity]] = defaultdict(list)
    for entity in entities:
        label = normalize_reference_label(entity.display_name)
        if label and entity.type in REFERENCE_TARGET_TYPES:
            labels[label][(entity.type, entity.name)] += 1
            evidence.setdefault((label, entity.type, entity.name), entity)
        if entity.description_uid:
            owners[entity.description_uid].append(entity)

    known_tag_labels = set(build_named_reference_lexicon(russian_entries))
    unique_labels: dict[str, SourceEntity] = {}
    for label, targets in labels.items():
        if len(targets) != 1 or label in known_tag_labels:
            continue
        (tooltip_type, tooltip), _ = targets.most_common(1)[0]
        unique_labels[label] = evidence[(label, tooltip_type, tooltip)]

    patterns = {label: compile_reference_pattern(label) for label in unique_labels}
    findings: list[dict[str, object]] = []
    for content_uid, owner_entities in sorted(owners.items()):
        entry = russian_entries.get(content_uid)
        if entry is None:
            continue
        unlinked_text = LSTAG_PATTERN.sub(" ", entry["text"])
        normalized_unlinked_text = WHITESPACE_PATTERN.sub(" ", unlinked_text).casefold()
        owner_targets = {(owner.type, owner.name) for owner in owner_entities}
        for label, pattern in patterns.items():
            match = pattern.search(normalized_unlinked_text)
            if match is None:
                continue
            target = unique_labels[label]
            if (target.type, target.name) in owner_targets:
                continue
            context_start = max(0, match.start() - 60)
            context_end = min(len(normalized_unlinked_text), match.end() + 60)
            context = normalized_unlinked_text[context_start:context_end]
            if target.type == "Skills":
                confidence = (
                    "high"
                    if re.search(r"навык|провер|владен|экспертност", context)
                    else "low"
                )
                reason = "skill_reference_with_rules_context" if confidence == "high" else "ambiguous_skill_word"
            elif " " in label:
                confidence = "high"
                reason = "unique_multiword_entity_name"
            else:
                confidence = "medium"
                reason = "unique_single_word_entity_name"
            findings.append(
                {
                    "contentuid": content_uid,
                    "version": entry["version"],
                    "label": label,
                    "suggestedType": target.type,
                    "suggestedTooltip": target.name,
                    "displayNameContentuid": target.display_uid,
                    "sourceFile": target.source_file,
                    "confidence": confidence,
                    "reason": reason,
                    "ownerEntities": sorted(
                        {f"{owner.type}:{owner.name}" for owner in owner_entities}
                    ),
                    "russianText": entry["text"],
                }
            )
    return findings


def count_tags(entries: Iterable[dict[str, str]]) -> int:
    return sum(len(extract_tooltip_tags(entry["text"])) for entry in entries)


def build_report(
    *,
    english_entries: dict[str, dict[str, str]],
    russian_entries: dict[str, dict[str, str]],
    source_entities: list[SourceEntity] | None = None,
) -> dict[str, object]:
    tooltip_target_differences = audit_preservation(english_entries, russian_entries)
    preservation_issues = [
        issue for issue in tooltip_target_differences if issue["missingFromRussian"]
    ]
    additional_tooltip_targets = [
        issue for issue in tooltip_target_differences if issue["extraInRussian"]
    ]
    binding_issues = audit_russian_binding(russian_entries)
    terminology_issues = audit_tooltip_terminology(russian_entries)
    terminology_issues.extend(
        audit_cross_language_terminology(english_entries, russian_entries)
    )
    skill_reference_issues = audit_skill_references(
        english_entries,
        russian_entries,
    )
    unlinked_references = audit_unlinked_named_references(russian_entries)
    source_catalog_references = (
        audit_source_catalog_references(
            entities=source_entities,
            russian_entries=russian_entries,
        )
        if source_entities is not None
        else []
    )
    high_confidence_source_references = sum(
        finding["confidence"] == "high" for finding in source_catalog_references
    )
    source_entities_by_type = Counter(
        entity.type for entity in (source_entities or [])
    )
    source_descriptions_by_type: dict[str, int] = {}
    for entity_type in sorted(source_entities_by_type):
        source_descriptions_by_type[entity_type] = len(
            {
                entity.description_uid
                for entity in (source_entities or [])
                if entity.type == entity_type and entity.description_uid
            }
        )
    english_uids = set(english_entries)
    russian_uids = set(russian_entries)

    return {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(),
        "summary": {
            "englishEntries": len(english_entries),
            "russianEntries": len(russian_entries),
            "commonEntries": len(english_uids & russian_uids),
            "englishTooltipTags": count_tags(english_entries.values()),
            "russianTooltipTags": count_tags(russian_entries.values()),
            "preservationIssues": len(preservation_issues),
            "additionalRussianTooltipEntries": len(additional_tooltip_targets),
            "bindingIssues": len(binding_issues),
            "terminologyIssues": len(terminology_issues),
            "missingSkillReferences": len(skill_reference_issues),
            "unlinkedNamedReferenceCandidates": len(unlinked_references),
            "sourceCatalogEntities": len(source_entities or []),
            "sourceCatalogEntitiesByType": dict(sorted(source_entities_by_type.items())),
            "sourceDescriptionsByType": source_descriptions_by_type,
            "sourceCatalogReferenceCandidates": len(source_catalog_references),
            "highConfidenceSourceCatalogCandidates": high_confidence_source_references,
            "englishOnlyEntries": len(english_uids - russian_uids),
            "russianOnlyEntries": len(russian_uids - english_uids),
        },
        "preservationIssues": preservation_issues,
        "additionalRussianTooltipTargets": additional_tooltip_targets,
        "bindingIssues": binding_issues,
        "terminologyIssues": terminology_issues,
        "missingSkillReferences": skill_reference_issues,
        "unlinkedNamedReferenceCandidates": unlinked_references,
        "sourceCatalogReferenceCandidates": source_catalog_references,
        "englishOnlyContentuids": sorted(english_uids - russian_uids),
        "russianOnlyContentuids": sorted(russian_uids - english_uids),
    }


def build_reviewer_input(
    *,
    binding_issues: list[dict[str, str]],
    english_entries: dict[str, dict[str, str]],
) -> dict[str, object]:
    issues_by_uid: dict[str, list[dict[str, str]]] = defaultdict(list)
    for issue in binding_issues:
        issues_by_uid[issue["contentuid"]].append(issue)

    items: list[dict[str, object]] = []
    for content_uid, issues in sorted(issues_by_uid.items()):
        current = issues[0]
        english_entry = english_entries.get(content_uid, {"text": ""})
        items.append(
            {
                "contentuid": content_uid,
                "english_text": english_entry["text"],
                "current_russian_text": current["russianText"],
                "required_glossary_terms": [],
                "binding_findings": [
                    {
                        "tooltip": issue["tooltip"],
                        "label": issue["label"],
                        "expectedRussianRoots": issue["expectedRussianRoots"],
                    }
                    for issue in issues
                ],
            }
        )
    return {"itemCount": len(items), "items": items}


def main() -> int:
    args = parse_args()
    try:
        english_entries = read_localization(Path(args.english_path))
        russian_entries = read_localization(Path(args.russian_path))
        source_entities = (
            build_source_entities(
                stats_path=Path(args.stats_path),
                russian_entries=russian_entries,
            )
            if str(args.stats_path).strip()
            else None
        )
        if str(args.root_templates_path).strip():
            if source_entities is None:
                source_entities = []
            source_entities.extend(
                build_root_template_entities(
                    root_templates_path=Path(args.root_templates_path),
                    russian_entries=russian_entries,
                )
            )
        report = build_report(
            english_entries=english_entries,
            russian_entries=russian_entries,
            source_entities=source_entities,
        )
        output_path = Path(args.output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        reviewer_input_path = Path(args.reviewer_input_path).resolve()
        reviewer_input_path.parent.mkdir(parents=True, exist_ok=True)
        reviewer_input_path.write_text(
            json.dumps(
                build_reviewer_input(
                    binding_issues=report["bindingIssues"],
                    english_entries=english_entries,
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        print(exc, file=sys.stderr)
        return 1

    summary = report["summary"]
    print(
        "[audit-tooltip-links.py] "
        f"preservation={summary['preservationIssues']}; "
        f"additional_ru_tooltip_entries={summary['additionalRussianTooltipEntries']}; "
        f"binding={summary['bindingIssues']}; "
        f"terminology={summary['terminologyIssues']}; "
        f"missing_skill_references={summary['missingSkillReferences']}; "
        f"unlinked_candidates={summary['unlinkedNamedReferenceCandidates']}; "
        f"source_catalog_candidates={summary['sourceCatalogReferenceCandidates']}; "
        f"report='{output_path}'; reviewer_input='{reviewer_input_path}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
