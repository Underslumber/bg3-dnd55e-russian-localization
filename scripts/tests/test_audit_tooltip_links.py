from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "audit-tooltip-links.py"
SPEC = importlib.util.spec_from_file_location("audit_tooltip_links", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
AUDIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = AUDIT
SPEC.loader.exec_module(AUDIT)


def entry(text: str, version: str = "1") -> dict[str, str]:
    return {"text": text, "version": version}


def test_preservation_ignores_valid_russian_word_order_change() -> None:
    english = {
        "uid": entry(
            '<LSTag Tooltip="Charisma">Charisma</LSTag> '
            '<LSTag Tooltip="AbilityModifier">Modifier</LSTag>'
        )
    }
    russian = {
        "uid": entry(
            '<LSTag Tooltip="AbilityModifier">модификатор</LSTag> '
            '<LSTag Tooltip="Charisma">Харизмы</LSTag>'
        )
    }

    assert AUDIT.audit_preservation(english, russian) == []
    assert AUDIT.audit_russian_binding(russian) == []


def test_binding_detects_tags_left_on_reordered_words() -> None:
    russian = {
        "uid": entry(
            '<LSTag Tooltip="Intelligence">проверки</LSTag> '
            '<LSTag Tooltip="AbilityCheck">Интеллекта</LSTag>'
        )
    }

    issues = AUDIT.audit_russian_binding(russian)

    assert [(issue["tooltip"], issue["label"]) for issue in issues] == [
        ("Intelligence", "проверки"),
        ("AbilityCheck", "Интеллекта"),
    ]


def test_binding_accepts_inflected_ability_check_phrase() -> None:
    russian = {
        "uid": entry(
            '<LSTag Tooltip="AbilityCheck">проверок характеристик</LSTag>'
        )
    }

    assert AUDIT.audit_russian_binding(russian) == []


def test_tooltip_terminology_uses_project_glossary_terms() -> None:
    russian = {
        "bad": entry(
            '<LSTag Tooltip="HitPoints">очки здоровья</LSTag> и '
            '<LSTag Tooltip="OpportunityAttack">атака по возможности</LSTag>'
        ),
        "good": entry(
            '<LSTag Tooltip="HitPoints">ОЗ</LSTag> и '
            '<LSTag Tooltip="OpportunityAttack">внеочередная атака</LSTag>'
        ),
    }

    issues = AUDIT.audit_tooltip_terminology(russian)

    assert [(issue["contentuid"], issue["tooltip"]) for issue in issues] == [
        ("bad", "HitPoints"),
        ("bad", "OpportunityAttack"),
    ]


def test_cross_language_terminology_flags_non_glossary_perception() -> None:
    english = {"uid": entry("Make a Perception check.")}
    russian = {"uid": entry("Совершите проверку Внимательности.")}

    issues = AUDIT.audit_cross_language_terminology(english, russian)

    assert len(issues) == 1
    assert issues[0]["preferredTerm"] == "Внимание"


def test_skill_reference_audit_uses_english_context_and_russian_inflection() -> None:
    english = {
        "skill": entry("You gain proficiency in the Insight and Medicine skills."),
        "ordinary": entry("Arcana fills the old tower."),
    }
    russian = {
        "skill": entry("Вы получаете владение навыками Проницательности и Медицины."),
        "ordinary": entry("Магия наполняет старую башню."),
    }

    findings = AUDIT.audit_skill_references(english, russian)

    assert [(issue["suggestedTooltip"], issue["label"]) for issue in findings] == [
        ("Insight", "Проницательности"),
        ("Medicine", "Медицины"),
    ]


def test_skill_reference_audit_skips_existing_skill_tooltip() -> None:
    english = {"uid": entry("You gain proficiency in the Stealth skill.")}
    russian = {
        "uid": entry(
            'Вы получаете владение навыком '
            '<LSTag Type="Skills" Tooltip="Stealth">Скрытность</LSTag>.'
        )
    }

    assert AUDIT.audit_skill_references(english, russian) == []


def test_skill_reference_audit_chooses_term_nearest_rules_context() -> None:
    english = {
        "uid": entry(
            "Your bond with nature grants a bonus to Intelligence "
            "(Arcana or Nature) checks."
        )
    }
    russian = {
        "uid": entry(
            "Связь с природой дает бонус к проверкам Интеллекта "
            "(Магия или Природа)."
        )
    }

    findings = AUDIT.audit_skill_references(english, russian)

    nature = next(item for item in findings if item["suggestedTooltip"] == "Nature")
    assert nature["label"] == "Природа"


def test_skill_reference_audit_rejects_distant_ordinary_word() -> None:
    english = {
        "uid": entry(
            "Imbue the weapon with nature's power. The weapon keeps its normal "
            "damage die and remains suitable for every ordinary melee attack. "
            "Much later, use a weapon "
            "with which you have proficiency as a Spellcasting Focus."
        )
    }
    russian = {
        "uid": entry(
            "Наделите оружие силой природы. Значительно позже используйте "
            "оружие, которым владеете, как магическую фокусировку."
        )
    }

    assert AUDIT.audit_skill_references(english, russian) == []


def test_preservation_reports_changed_target() -> None:
    english = {
        "uid": entry('<LSTag Type="Status" Tooltip="BLINDED">Blinded</LSTag>')
    }
    russian = {
        "uid": entry('<LSTag Type="Status" Tooltip="POISONED">Слепота</LSTag>')
    }

    issues = AUDIT.audit_preservation(english, russian)

    assert len(issues) == 1
    assert issues[0]["missingFromRussian"] == [
        {"type": "Status", "tooltip": "BLINDED", "count": 1}
    ]
    assert issues[0]["extraInRussian"] == [
        {"type": "Status", "tooltip": "POISONED", "count": 1}
    ]


def test_report_allows_reviewed_russian_only_tooltip_addition() -> None:
    english = {"uid": entry("Невидимость")}
    russian = {
        "uid": entry(
            '<LSTag Type="Status" Tooltip="INVISIBLE">Невидимость</LSTag>'
        )
    }

    report = AUDIT.build_report(
        english_entries=english,
        russian_entries=russian,
    )

    assert report["summary"]["preservationIssues"] == 0
    assert report["summary"]["additionalRussianTooltipEntries"] == 1
    assert report["preservationIssues"] == []
    assert len(report["additionalRussianTooltipTargets"]) == 1


def test_unlinked_named_reference_uses_existing_unique_target_as_evidence() -> None:
    russian = {
        "source": entry(
            '<LSTag Type="Spell" Tooltip="Target_Haste">Ускорение</LSTag>'
        ),
        "candidate": entry('Вы всегда держите заклинание «Ускорение» подготовленным.'),
    }

    findings = AUDIT.audit_unlinked_named_references(russian)

    assert len(findings) == 1
    assert findings[0]["contentuid"] == "candidate"
    assert findings[0]["suggestedType"] == "Spell"
    assert findings[0]["suggestedTooltip"] == "Target_Haste"
    assert findings[0]["evidenceContentuid"] == "source"


def test_source_catalog_uses_skills_type_and_rules_context_confidence() -> None:
    entity = AUDIT.SourceEntity(
        type="Skills",
        name="Stealth",
        display_uid="stealth_name",
        display_name="Скрытность",
        description_uid="stealth_description",
        source_file="Passive.txt",
    )
    owner = AUDIT.SourceEntity(
        type="Passive",
        name="PrimalKnowledge",
        display_uid="owner_name",
        display_name="Первобытное знание",
        description_uid="owner_description",
        source_file="Passive.txt",
    )
    russian = {
        "owner_description": entry("Вы получаете владение навыком Скрытность."),
    }

    findings = AUDIT.audit_source_catalog_references(
        entities=[entity, owner],
        russian_entries=russian,
    )

    assert len(findings) == 1
    assert findings[0]["suggestedType"] == "Skills"
    assert findings[0]["confidence"] == "high"


def test_source_catalog_finds_other_named_entity_in_description() -> None:
    entities = [
        AUDIT.SourceEntity(
            type="Spell",
            name="Target_Haste",
            display_uid="haste_name",
            display_name="Ускорение",
            description_uid="haste_description",
            source_file="Spell_Target.txt",
        ),
        AUDIT.SourceEntity(
            type="Passive",
            name="AlwaysHasted",
            display_uid="passive_name",
            display_name="Постоянное ускорение",
            description_uid="passive_description",
            source_file="Passive.txt",
        ),
    ]
    russian = {
        "haste_description": entry("Ускоряет выбранную цель."),
        "passive_description": entry(
            "Вы можете сотворить заклинание «Ускорение» после долгого отдыха."
        ),
    }

    findings = AUDIT.audit_source_catalog_references(
        entities=entities,
        russian_entries=russian,
    )

    assert len(findings) == 1
    assert findings[0]["contentuid"] == "passive_description"
    assert findings[0]["suggestedType"] == "Spell"
    assert findings[0]["suggestedTooltip"] == "Target_Haste"
    assert findings[0]["confidence"] == "medium"


def test_source_catalog_audits_item_description_without_using_item_as_target() -> None:
    entities = [
        AUDIT.SourceEntity(
            type="Spell",
            name="Target_Haste",
            display_uid="haste_name",
            display_name="Ускорение",
            description_uid="haste_description",
            source_file="Spell_Target.txt",
        ),
        AUDIT.SourceEntity(
            type="Armor",
            name="MAG_Haste_Robe",
            display_uid="robe_name",
            display_name="Одеяние ускорения",
            description_uid="robe_description",
            source_file="Armor.txt",
        ),
    ]
    russian = {
        "haste_description": entry("Ускоряет выбранную цель."),
        "robe_description": entry(
            "Владелец может сотворить заклинание «Ускорение»."
        ),
    }

    findings = AUDIT.audit_source_catalog_references(
        entities=entities,
        russian_entries=russian,
    )

    assert len(findings) == 1
    assert findings[0]["ownerEntities"] == ["Armor:MAG_Haste_Robe"]
    assert findings[0]["suggestedType"] == "Spell"
    assert findings[0]["suggestedTooltip"] == "Target_Haste"


def test_root_templates_add_item_description_owners(tmp_path: Path) -> None:
    template = tmp_path / "robe.lsx"
    template.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<save><region id="Templates"><node id="Templates"><children>
<node id="GameObjects">
  <attribute id="MapKey" value="item-guid" />
  <attribute id="Name" value="MAG_Haste_Robe" />
  <attribute id="Type" value="item" />
  <attribute id="DisplayName" handle="robe_name" />
  <attribute id="Description" handle="robe_description" />
</node>
</children></node></region></save>
""",
        encoding="utf-8",
    )
    russian = {
        "robe_name": entry("Одеяние ускорения"),
        "robe_description": entry("Позволяет сотворить Ускорение."),
    }

    entities = AUDIT.build_root_template_entities(
        root_templates_path=tmp_path,
        russian_entries=russian,
    )

    assert len(entities) == 1
    assert entities[0].type == "ItemTemplate"
    assert entities[0].name == "MAG_Haste_Robe"
    assert entities[0].description_uid == "robe_description"
