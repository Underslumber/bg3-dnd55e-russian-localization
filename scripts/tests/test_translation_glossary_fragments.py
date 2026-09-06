import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "fill-translation-openrouter.py"
SPEC = importlib.util.spec_from_file_location("fill_translation_openrouter", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def preserves_term(term: str, translated_text: str) -> bool:
    fragments = MODULE.extract_russian_term_fragments(term)
    normalized = MODULE.normalize_russian_for_match(translated_text)
    return bool(fragments) and all(fragment in normalized for fragment in fragments)


def test_short_adjective_is_cut_before_its_ending():
    assert MODULE.extract_russian_term_fragments("Дикий облик") == ["дик", "обли"]


def test_oblique_cases_of_short_adjective_are_accepted():
    for text in (
        "Дикий облик",
        "Находясь в Диком облике, вы получаете следующие преимущества.",
        "Каждая из ваших атак в форме Дикого облика наносит урон Излучением.",
        "Вы управляете Диким обликом.",
    ):
        assert preserves_term("Дикий облик", text), text


def test_unrelated_translation_is_still_rejected():
    assert not preserves_term("Дикий облик", "Вы принимаете звериную форму.")


def test_longer_words_keep_the_previous_fragment_cut():
    assert MODULE.extract_russian_term_fragments("Спасбросок от смерти") == ["спасброс", "смер"]
    assert MODULE.extract_russian_term_fragments("Невидимость") == ["невидим"]


def test_assert_translation_quality_accepts_inflected_glossary_term():
    MODULE.assert_translation_quality(
        "h334bd2c8g7709g2b93g78b1g773fe3b8ebf1",
        "Each of your attacks in a Wild Shape form can deal its normal damage type or Radiant damage.",
        "Каждая из ваших атак в форме Дикого облика может наносить свой обычный тип урона или урон Излучением.",
        {"Wild Shape": "Дикий облик"},
    )


def test_specific_spell_slot_heading_overrides_nested_glossary_term():
    selected = MODULE.select_relevant_glossary(
        {
            "Spell Slots": "Ячейки заклинаний",
            "Recovering Spell Slots": "Восстановление ячеек заклинаний",
        },
        ["Recovering Spell Slots"],
    )

    assert selected == {
        "Recovering Spell Slots": "Восстановление ячеек заклинаний",
    }
    MODULE.assert_translation_quality(
        "hc923040bgca3dgc5c9g86f9g4961f50ef2b1",
        "Recovering Spell Slots",
        "Восстановление ячеек заклинаний",
        selected,
    )
