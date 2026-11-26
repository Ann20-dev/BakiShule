"""Every key must exist in both languages with the same {placeholders}."""
import pytest

from app.messages import MESSAGES, format_date, join_list, placeholders, t


def test_both_languages_have_identical_keys():
    en, sw = set(MESSAGES["en"]), set(MESSAGES["sw"])
    assert not en - sw, f"Missing in sw: {sorted(en - sw)}"
    assert not sw - en, f"Missing in en: {sorted(sw - en)}"


@pytest.mark.parametrize("key", sorted(MESSAGES["en"]))
def test_placeholders_match(key):
    assert placeholders(MESSAGES["en"][key]) == placeholders(MESSAGES["sw"][key]), key


def test_no_empty_translations():
    for lang, table in MESSAGES.items():
        assert all(value.strip() for value in table.values()), lang


def test_swahili_dates_and_lists():
    from datetime import date

    wednesday = date(2026, 11, 25)
    assert format_date(wednesday, "sw") == "Jumatano 25 Nov"
    assert format_date(wednesday, "en") == "Wednesday 25 Nov"
    assert format_date(date(2026, 8, 3), "sw") == "Jumatatu 3 Ago"
    days = ["Jumatatu", "Jumanne", "Jumatano", "Alhamisi", "Ijumaa", "Jumamosi", "Jumapili"]
    assert t("weekdays", "sw").split(",") == days
    assert join_list(["Jumatatu", "Jumanne"], "sw") == "Jumatatu na Jumanne"
    assert join_list(["Monday", "Tuesday", "Friday"], "en") == "Monday, Tuesday and Friday"


def test_unknown_language_falls_back_to_english():
    assert t("saved", None) == "Saved" and t("saved", "fr") == "Saved"
    assert t("saved", "sw") == "Imehifadhiwa"
