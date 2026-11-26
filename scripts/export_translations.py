"""Write TRANSLATIONS.md: every user-facing string side by side (English | Kiswahili) for review.

    .venv/bin/python -m scripts.export_translations
"""
from pathlib import Path

from app.messages import MESSAGES

SECTIONS = [
    ("Language selection & shared (shown before a language is known)",
     ("language_screen", "not_registered", "sms_welcome", "lang_prompt", "language_name", "language_changed")),
    ("Dates", ("weekdays", "weekdays_short", "months", "date_long", "date_short", "list_and")),
    ("USSD navigation & common", ("nav_", "invalid_choice", "no_class", "saved", "option_")),
    ("Teacher USSD menu", ("teacher_menu", "menu_change_language", "select_class", "done_today")),
    ("Teacher USSD: attendance", ("att_screen", "att_already", "att_enter", "att_all", "att_unknown", "att_roll",
                                   "att_confirm", "att_counts", "att_absent", "more", "att_cancelled",
                                   "att_invalid", "att_saved", "att_flagged", "att_parents")),
    ("Teacher USSD: class summary, at-risk, lookup", ("sum_", "ar_", "level_", "det_", "lookup_")),
    ("Risk reasons (USSD detail, teacher alerts)", ("reason_",)),
    ("Behaviour logging, codes & subjects", ("beh_choose", "beh_no_roll", "beh_enter", "beh_invalid", "beh_subject",
                                             "beh_saved", "beh_parent", "behaviour_", "subject_", "teacher_title")),
    ("Parent USSD", ("parent_menu", "choose_child", "enter_pin", "contact_")),
    ("SMS: menu, PIN & limits", ("menu", "rate_limited", "pin_", "no_pin", "choose_child_sms", "combined_hint")),
    ("SMS: STATUS (HALI)", ("status_", "today_", "last_note", "no_notes", "short_")),
    ("SMS: ATT (MAHUDHURIO)", ("att_week_line", "att_missed_days", "att_no_missed", "att_term_line",
                               "att_class_avg", "att_short")),
    ("SMS: BEHAVIOUR (TABIA)", ("beh_header", "beh_none")),
    ("SMS: REPORT (RIPOTI)", ("report_", "risk_", "tip_", "fallback_")),
    ("SMS: check-ins, acknowledgements, alerts, receipts",
     ("checkin", "ack_", "alert_", "teacher_parent", "reward_", "sponsor_")),
]


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", "<br>")


def main() -> None:
    en, sw = MESSAGES["en"], MESSAGES["sw"]
    used: set[str] = set()
    lines = [
        "# BakiShule translations (English / Kiswahili)",
        "",
        "Generated from `app/messages.py` by `python -m scripts.export_translations`. Please review the",
        "Kiswahili column before the demo and send corrections against the **key**. `{placeholders}` are filled",
        "in by the app and must stay as they are; `<br>` marks a line break. Emojis are replaced by plain text",
        "(⭐→*, ⚠️→!, ✅→OK, ⬇️/⬆️→chini/juu) when an SMS would exceed 2 segments.",
        "",
        f"Total strings: {len(en)}.",
        "",
    ]
    for title, prefixes in SECTIONS:
        keys = [key for key in en if key not in used and any(
            key == prefix or (prefix.endswith("_") and key.startswith(prefix)) or key.startswith(prefix)
            for prefix in prefixes)]
        if not keys:
            continue
        used.update(keys)
        lines += [f"## {title}", "", "| Key | English | Kiswahili |", "|---|---|---|"]
        lines += [f"| `{key}` | {_cell(en[key])} | {_cell(sw[key])} |" for key in keys]
        lines.append("")
    rest = [key for key in en if key not in used]
    if rest:
        lines += ["## Other", "", "| Key | English | Kiswahili |", "|---|---|---|"]
        lines += [f"| `{key}` | {_cell(en[key])} | {_cell(sw[key])} |" for key in rest]
        lines.append("")
    Path("TRANSLATIONS.md").write_text("\n".join(lines))
    print(f"Wrote TRANSLATIONS.md ({len(en)} strings)")


if __name__ == "__main__":
    main()
