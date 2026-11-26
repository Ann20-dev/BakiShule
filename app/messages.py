"""Every user-facing USSD and SMS string, in English (en) and Kiswahili (sw).

Rules
- Both languages MUST have the same keys and the same {placeholders}
  (tests/test_translations.py enforces this).
- Get text only through t(key, lang, **params). Never hard-code user-facing text elsewhere.
- Emojis (⭐ ⚠️ ✅ ⬇️ ⬆️ 🟢 🟡 🟠 🔴) force UCS-2 SMS encoding; app/services/sms_format.py swaps
  them for plain text when a reply would exceed 2 segments (or when SMS_USE_EMOJI=false).
- Run `python -m scripts.export_translations` after editing to refresh TRANSLATIONS.md.
"""
from datetime import date
from string import Formatter

LANGUAGES = ("en", "sw")
DEFAULT_LANGUAGE = "en"

POSITIVE = "⭐"
CONCERN = "⚠️"
PRESENT_ICON = "✅"
DOWN = "⬇️"
UP = "⬆️"
RISK_ICONS = {"green": "🟢", "watch": "🟡", "at_risk": "🟠", "critical": "🔴"}

# Shown before a language is known: identical text in both tables.
_LANGUAGE_SCREEN = "Karibu BakiShule / Welcome\nChagua lugha / Choose language:\n1. English\n2. Kiswahili"
_NOT_REGISTERED = (
    "Namba hii haijasajiliwa. Tafadhali wasiliana na shule yako. / "
    "This number is not registered. Please contact your school."
)
_SMS_WELCOME = (
    "Karibu BakiShule! Tuma KISWAHILI au ENGLISH kuchagua lugha. / "
    "Reply ENGLISH or KISWAHILI to choose your language."
)
_LANG_PROMPT = "Tuma LUGHA SW au LANG EN. / Send LANG EN or LUGHA SW."

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # ===== shared / bilingual =====
        "language_screen": _LANGUAGE_SCREEN,
        "not_registered": _NOT_REGISTERED,
        "sms_welcome": _SMS_WELCOME,
        "lang_prompt": _LANG_PROMPT,
        "language_name": "English",
        "language_changed": "Language: English",
        # ===== dates =====
        "weekdays": "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday",
        "weekdays_short": "Mon,Tue,Wed,Thu,Fri,Sat,Sun",
        "months": "Jan,Feb,Mar,Apr,May,Jun,Jul,Aug,Sep,Oct,Nov,Dec",
        "date_long": "{weekday} {day} {month}",
        "date_short": "{weekday} {day} {month}",
        "list_and": "{items} and {last}",
        # ===== USSD navigation & common =====
        "nav_back": "0. Back",
        "nav_home": "00. Main menu",
        "invalid_choice": "Invalid choice, try again.",
        "no_class": "No class is assigned to this number.",
        "saved": "Saved",
        # ===== teacher main menu =====
        "teacher_menu_title": "BakiShule - Teacher",
        "teacher_menu_1": "Mark attendance",
        "teacher_menu_2": "Class summary",
        "teacher_menu_3": "At-risk learners",
        "teacher_menu_4": "Log behaviour",
        "teacher_menu_5": "Find learner",
        "teacher_menu_parent": "Parent menu",
        "menu_change_language": "Change language / Badilisha lugha",
        "select_class": "Select class:",
        "done_today": "done today",
        # ===== attendance =====
        "att_screen_header": "{cls} - {date} ({total} learners)",
        "att_already_marked": "Already marked today; this replaces it.",
        "att_enter": "Enter absent roll numbers e.g. 03 07 12",
        "att_all_present": "0 = all present",
        "att_enter_blank": "Enter absent roll numbers e.g. 03 07 12, or 0 if all present.",
        "att_unknown_roll": "Unknown roll: {rolls}.",
        "att_roll_range": "{cls} rolls are {first}-{last}.",
        "att_enter_again": "Enter absent roll numbers again.",
        "att_confirm": "Confirm {cls} {date}:",
        "att_counts": "Present {present}/{total}, absent {absent}",
        "att_absent_list": "Absent: {names}",
        "more": "+{count} more",
        "option_save": "1. Save",
        "option_cancel": "0. Cancel",
        "att_cancelled": "Attendance cancelled. Nothing was saved.",
        "att_invalid_roll": "Invalid roll number. No attendance saved.",
        "att_saved": "Saved attendance for {count} learners in {cls}.",
        "att_saved_counts": "Present {present}, absent {absent}.",
        "att_flagged": "Flagged in class: {count}.",
        "att_parents_notified": "Parents of {count} absent flagged learner(s) will get an SMS.",
        "att_invalid_entry": "Invalid attendance entry. Dial again.",
        # ===== class summary =====
        "sum_header": "{cls} - {date}",
        "sum_today": "Today: {present} present, {absent} absent ({pct})",
        "sum_unmarked": "Today: not yet marked",
        "sum_week": "This week: {pct}",
        "sum_month": "Last 30 days: {pct}",
        "sum_flagged": "Flagged: {count} ({critical} critical)",
        "sum_absent": "Absent: {rolls}",
        # ===== at-risk / learner detail =====
        "ar_none": "No flagged learners in {cls}. Keep it up!",
        "ar_header": "{cls} flagged ({count}):",
        "ar_reply_for_details": "Reply number for details",
        "level_green": "OK",
        "level_watch": "WATCH",
        "level_at_risk": "AT RISK",
        "level_critical": "CRITICAL",
        "det_risk": "Risk: {level} {score}/100",
        "det_30_days": "30 days: {pct} present, {absent} absent",
        "det_last_absent": "Last absent: {date}",
        "det_parent_said": "Parent said: {text}",
        "det_guardian": "Guardian: {name} {phone}",
        "lookup_enter_roll": "{cls}: enter learner roll number",
        "lookup_not_found": "No learner with roll {roll} in {cls}.",
        # ===== risk reasons (USSD detail, teacher alerts) =====
        "reason_streak": "{count} absences in a row",
        "reason_drop": "Attendance down {pct} (last 2 wks)",
        "reason_weekday": "Often absent on {weekday}",
        "reason_monthly": "Monthly absence clusters",
        "reason_sibling": "Sibling absent on {count} same days",
        "reason_fees": "Parent reported fee difficulty",
        "reason_behaviour": "{count} behaviour concerns in {days} days",
        "reason_default": "Attendance risk increased",
        # ===== behaviour logging =====
        "beh_no_roll": "No roll {roll} in {cls}.",
        "beh_enter_again": "Enter roll number again:",
        "beh_choose": "{roll} {name}: choose",
        "beh_invalid_code": "Invalid behaviour code, try again.",
        "beh_subject_title": "Subject (optional):",
        "option_skip": "0. Skip",
        "beh_invalid_subject": "Invalid subject, try again.",
        "beh_saved": "Saved for {roll} {name}:",
        "beh_parent_can_view": "Parent can see it by SMS (BEHAVIOUR).",
        "behaviour_1": "Participated well",
        "behaviour_2": "Homework not done",
        "behaviour_3": "Late",
        "behaviour_4": "Disruptive",
        "behaviour_5": "Helped others",
        "behaviour_6": "Excellent test score",
        "behaviour_short_1": "Participated",
        "behaviour_short_2": "No homework",
        "behaviour_short_3": "Late",
        "behaviour_short_4": "Disruptive",
        "behaviour_short_5": "Helped others",
        "behaviour_short_6": "Top test score",
        "subject_1": "Maths",
        "subject_2": "English",
        "subject_3": "Kiswahili",
        "subject_4": "Science",
        "subject_5": "Social Studies",
        "subject_6": "CRE",
        "teacher_title": "Tr. {surname}",
        # ===== parent USSD =====
        "parent_menu_title": "BakiShule - {name}",
        "parent_menu_1": "Today's status",
        "parent_menu_2": "Attendance",
        "parent_menu_3": "Behaviour",
        "parent_menu_4": "Weekly report",
        "parent_menu_5": "Contact school",
        "choose_child": "Choose child:",
        "enter_pin": "Enter your PIN:",
        "contact_prompt": "Type your message to the school:",
        "contact_sent": "Sent. The class teacher will get back to you.",
        "contact_empty": "Message was empty. Nothing sent.",
        # ===== SMS menu & errors =====
        "menu": (
            "BakiShule SMS:\n"
            "STATUS - today\n"
            "ATT - attendance\n"
            "BEHAVIOUR <PIN> - behaviour\n"
            "REPORT <PIN> - weekly report\n"
            "LANG SW - Kiswahili\n"
            "STOP - no more SMS"
        ),
        "rate_limited": "BakiShule: you have reached today's limit of {limit} requests. Please try again tomorrow.",
        "pin_required": "Please add your 4-digit PIN, e.g. {example}",
        "pin_wrong": "Wrong PIN. {left} attempt(s) left before a 1-hour lock.",
        "pin_locked": "Too many wrong PINs. Please try again after {time}.",
        "no_pin": "No PIN is set for this number. Please ask the school for your PIN.",
        "pin_only": "To use your PIN, send it after a command, e.g. REPORT {example}.",
        "choose_child_sms": "You have {count} children: {children}. Send {example}",
        "combined_hint": "Send {command} 1 for details.",
        # ===== SMS: STATUS =====
        "status_line": "{name} ({cls}) - {date}: {today}",
        "today_present": "{icon} At school today.",
        "today_absent": "{icon} Not at school today.",
        "today_unmarked": "Today's attendance is not marked yet.",
        "last_note": "Last note: {icon} {label}{subject} ({teacher}).",
        "no_notes": "No behaviour notes yet.",
        "status_more": "Send ATT, BEHAVIOUR or REPORT for more.",
        "status_short": "{name}: {today}",
        "short_present": "at school today",
        "short_absent": "not at school today",
        "short_unmarked": "not marked yet",
        # ===== SMS: ATT =====
        "att_week_line": "{name} - This week: {attended}/{total} days ({missed}).",
        "att_missed_days": "missed {days}",
        "att_no_missed": "no days missed",
        "att_term_line": "Term: {pct}.",
        "att_class_avg": "Class average: {pct}.",
        "att_short": "{name}: {attended}/{total} days this week, term {pct}",
        # ===== SMS: BEHAVIOUR =====
        "beh_header": "{name} - Behaviour this term: {positive}{pos} {concern}{con}",
        "beh_none": "No behaviour notes yet this term.",
        # ===== SMS: REPORT =====
        "report_title": "Weekly report - {name}, {cls}:",
        "report_attendance": "Attendance {pct}{arrow} (was {previous}).",
        "report_attendance_same": "Attendance {pct} (same as last week).",
        "report_attendance_only": "Attendance {pct}.",
        "report_behaviour": "Behaviour {positive}{pos} {concern}{con}.",
        "report_status": "Status: {icon}{risk}.",
        "risk_green": "On track",
        "risk_watch": "Watch",
        "risk_at_risk": "At risk",
        "risk_critical": "High risk",
        "risk_none": "Not scored yet",
        "tip_attendance": "Tip: Ask {first} about {day}. Send 2 if fees are a challenge.",
        "tip_behaviour": "Tip: Talk with {first} about behaviour in class.",
        "tip_checkin": "Tip: A short daily chat about school helps {first}.",
        "tip_praise": "Tip: Great week! Tell {first} you are proud of them.",
        "fallback_down": "down",
        "fallback_up": "up",
        # ===== SMS: check-ins, acks, alerts =====
        "checkin": "We missed {name} {days}. Is everything okay? Reply 1 Sick, 2 Fees, 3 Other.",
        "checkin_on_days": "on {days}",
        "checkin_for_days": "for {count} school days",
        "ack_1": "Thank you. Get well soon, {names}! The class teacher has been informed.",
        "ack_2": "Thank you for telling us. The school will contact you about fee support for {names}.",
        "ack_3": "Thank you. Your message about {names} has been passed to the class teacher. Send MENU for options.",
        "ack_start": "You will get BakiShule updates again. Send STOP to opt out.",
        "alert_at_risk": "At-risk: {name} ({cls}). {summary}",
        "alert_parent_reply": "Parent reply: {text}",
        "teacher_parent_sick": "Parent reports {name} is sick. Please follow up.",
        "teacher_parent_reply": "Parent reply about {name}: {text}",
        "teacher_parent_message": "Message from parent of {name}: {text}",
        "reward_congrats": "Congratulations {first}! You completed 4 weeks of full attendance. KES {amount} airtime is yours.",
        "sponsor_receipt": "Fee support of KES {amount} has been arranged for {name}.",
    },
    "sw": {
        "language_screen": _LANGUAGE_SCREEN,
        "not_registered": _NOT_REGISTERED,
        "sms_welcome": _SMS_WELCOME,
        "lang_prompt": _LANG_PROMPT,
        "language_name": "Kiswahili",
        "language_changed": "Lugha: Kiswahili",
        "weekdays": "Jumatatu,Jumanne,Jumatano,Alhamisi,Ijumaa,Jumamosi,Jumapili",
        "weekdays_short": "Jtt,Jnn,Jtn,Alh,Iju,Jms,Jpl",
        "months": "Jan,Feb,Mac,Apr,Mei,Jun,Jul,Ago,Sep,Okt,Nov,Des",
        "date_long": "{weekday} {day} {month}",
        "date_short": "{weekday} {day} {month}",
        "list_and": "{items} na {last}",
        "nav_back": "0. Rudi",
        "nav_home": "00. Menyu kuu",
        "invalid_choice": "Chaguo si sahihi, jaribu tena.",
        "no_class": "Hakuna darasa lililopewa namba hii.",
        "saved": "Imehifadhiwa",
        "teacher_menu_title": "BakiShule - Mwalimu",
        "teacher_menu_1": "Andika mahudhurio",
        "teacher_menu_2": "Muhtasari wa darasa",
        "teacher_menu_3": "Wanafunzi walio hatarini",
        "teacher_menu_4": "Andika tabia",
        "teacher_menu_5": "Tafuta mwanafunzi",
        "teacher_menu_parent": "Menyu ya mzazi",
        "menu_change_language": "Badilisha lugha",
        "select_class": "Chagua darasa:",
        "done_today": "imeandikwa leo",
        "att_screen_header": "{cls} - {date} (wanafunzi {total})",
        "att_already_marked": "Tayari imeandikwa leo; hii itaibadilisha.",
        "att_enter": "Andika namba za wasiokuja mf. 03 07 12",
        "att_all_present": "0 = wote wamekuja",
        "att_enter_blank": "Andika namba za wasiokuja mf. 03 07 12, au 0 kama wote wamekuja.",
        "att_unknown_roll": "Namba isiyojulikana: {rolls}.",
        "att_roll_range": "Namba za {cls} ni {first}-{last}.",
        "att_enter_again": "Andika namba za wasiokuja tena.",
        "att_confirm": "Thibitisha {cls} {date}:",
        "att_counts": "Wamekuja {present}/{total}, hawakuja {absent}",
        "att_absent_list": "Hawakuja: {names}",
        "more": "+{count} zaidi",
        "option_save": "1. Hifadhi",
        "option_cancel": "0. Ghairi",
        "att_cancelled": "Mahudhurio yameghairiwa. Hakuna kilichohifadhiwa.",
        "att_invalid_roll": "Namba si sahihi. Mahudhurio hayajahifadhiwa.",
        "att_saved": "Imehifadhiwa: mahudhurio ya wanafunzi {count} wa {cls}.",
        "att_saved_counts": "Wamekuja {present}, hawakuja {absent}.",
        "att_flagged": "Walio hatarini darasani: {count}.",
        "att_parents_notified": "Wazazi wa wanafunzi {count} walio hatarini watapata SMS.",
        "att_invalid_entry": "Mahudhurio si sahihi. Piga tena.",
        "sum_header": "{cls} - {date}",
        "sum_today": "Leo: {present} wamekuja, {absent} hawakuja ({pct})",
        "sum_unmarked": "Leo: bado haijaandikwa",
        "sum_week": "Wiki hii: {pct}",
        "sum_month": "Siku 30 zilizopita: {pct}",
        "sum_flagged": "Hatarini: {count} ({critical} hatari kubwa)",
        "sum_absent": "Hawakuja: {rolls}",
        "ar_none": "Hakuna walio hatarini {cls}. Hongera!",
        "ar_header": "{cls} walio hatarini ({count}):",
        "ar_reply_for_details": "Jibu namba kwa maelezo",
        "level_green": "SAWA",
        "level_watch": "ANGALIA",
        "level_at_risk": "HATARINI",
        "level_critical": "HATARI KUBWA",
        "det_risk": "Hatari: {level} {score}/100",
        "det_30_days": "Siku 30: alikuja {pct}, hakuja {absent}",
        "det_last_absent": "Hakuja mara ya mwisho: {date}",
        "det_parent_said": "Mzazi alisema: {text}",
        "det_guardian": "Mlezi: {name} {phone}",
        "lookup_enter_roll": "{cls}: andika namba ya mwanafunzi",
        "lookup_not_found": "Hakuna mwanafunzi namba {roll} katika {cls}.",
        "reason_streak": "Hakuja siku {count} mfululizo",
        "reason_drop": "Mahudhurio yameshuka {pct} (wiki 2)",
        "reason_weekday": "Hukosa shule {weekday} mara nyingi",
        "reason_monthly": "Hukosa shule kila mwezi",
        "reason_sibling": "Ndugu hakuja siku {count} hizo hizo",
        "reason_fees": "Mzazi alisema karo ni changamoto",
        "reason_behaviour": "Wasiwasi wa tabia {count} ndani ya siku {days}",
        "reason_default": "Hatari ya mahudhurio imeongezeka",
        "beh_no_roll": "Hakuna namba {roll} katika {cls}.",
        "beh_enter_again": "Andika namba tena:",
        "beh_choose": "{roll} {name}: chagua",
        "beh_invalid_code": "Chaguo si sahihi, jaribu tena.",
        "beh_subject_title": "Somo (si lazima):",
        "option_skip": "0. Ruka",
        "beh_invalid_subject": "Somo si sahihi, jaribu tena.",
        "beh_saved": "Imehifadhiwa kwa {roll} {name}:",
        "beh_parent_can_view": "Mzazi ataiona kwa SMS (TABIA).",
        "behaviour_1": "Alishiriki vizuri",
        "behaviour_2": "Hakufanya kazi ya nyumbani",
        "behaviour_3": "Alichelewa darasani",
        "behaviour_4": "Alisumbua darasani",
        "behaviour_5": "Aliwasaidia wenzake",
        "behaviour_6": "Alama bora mtihanini",
        "behaviour_short_1": "Alishiriki",
        "behaviour_short_2": "Hakufanya kazi",
        "behaviour_short_3": "Alichelewa",
        "behaviour_short_4": "Alisumbua",
        "behaviour_short_5": "Alisaidia wenzake",
        "behaviour_short_6": "Alama bora",
        "subject_1": "Hisabati",
        "subject_2": "Kiingereza",
        "subject_3": "Kiswahili",
        "subject_4": "Sayansi",
        "subject_5": "Masomo ya Jamii",
        "subject_6": "CRE",
        "teacher_title": "Mwl. {surname}",
        "parent_menu_title": "BakiShule - {name}",
        "parent_menu_1": "Hali ya leo",
        "parent_menu_2": "Mahudhurio",
        "parent_menu_3": "Tabia",
        "parent_menu_4": "Ripoti ya wiki",
        "parent_menu_5": "Wasiliana na shule",
        "choose_child": "Chagua mtoto:",
        "enter_pin": "Ingiza PIN yako:",
        "contact_prompt": "Andika ujumbe wako kwa shule:",
        "contact_sent": "Imetumwa. Mwalimu wa darasa atawasiliana nawe.",
        "contact_empty": "Ujumbe ulikuwa mtupu. Hakuna kilichotumwa.",
        "menu": (
            "BakiShule SMS:\n"
            "HALI - hali ya leo\n"
            "MAHUDHURIO - mahudhurio\n"
            "TABIA <PIN> - tabia\n"
            "RIPOTI <PIN> - ripoti ya wiki\n"
            "LUGHA EN - English\n"
            "ACHA - acha SMS"
        ),
        "rate_limited": "BakiShule: umefikia kikomo cha maombi {limit} leo. Tafadhali jaribu tena kesho.",
        "pin_required": "Tafadhali ongeza PIN yako ya tarakimu 4, mfano {example}",
        "pin_wrong": "PIN si sahihi. Majaribio {left} yamebaki kabla ya kufungiwa saa 1.",
        "pin_locked": "PIN zisizo sahihi nyingi. Jaribu tena baada ya saa {time}.",
        "no_pin": "Namba hii haina PIN. Tafadhali omba PIN yako shuleni.",
        "pin_only": "Tuma PIN pamoja na amri, mfano RIPOTI {example}.",
        "choose_child_sms": "Una watoto {count}: {children}. Tuma {example}",
        "combined_hint": "Tuma {command} 1 kwa maelezo zaidi.",
        "status_line": "{name} ({cls}) - {date}: {today}",
        "today_present": "{icon} Yuko shuleni leo.",
        "today_absent": "{icon} Hayupo shuleni leo.",
        "today_unmarked": "Mahudhurio ya leo bado hayajaandikwa.",
        "last_note": "Mwisho: {icon} {label}{subject} ({teacher}).",
        "no_notes": "Hakuna taarifa za tabia bado.",
        "status_more": "Tuma MAHUDHURIO, TABIA au RIPOTI kwa zaidi.",
        "status_short": "{name}: {today}",
        "short_present": "yuko shuleni leo",
        "short_absent": "hayupo shuleni leo",
        "short_unmarked": "bado haijaandikwa",
        "att_week_line": "{name} - Wiki hii: siku {attended}/{total} ({missed}).",
        "att_missed_days": "hakuja {days}",
        "att_no_missed": "hakukosa siku",
        "att_term_line": "Muhula: {pct}.",
        "att_class_avg": "Wastani wa darasa: {pct}.",
        "att_short": "{name}: siku {attended}/{total} wiki hii, muhula {pct}",
        "beh_header": "{name} - Tabia muhula huu: {positive}{pos} {concern}{con}",
        "beh_none": "Hakuna taarifa za tabia muhula huu.",
        "report_title": "Ripoti ya wiki - {name}, {cls}:",
        "report_attendance": "Mahudhurio {pct}{arrow} (ilikuwa {previous}).",
        "report_attendance_same": "Mahudhurio {pct} (sawa na wiki iliyopita).",
        "report_attendance_only": "Mahudhurio {pct}.",
        "report_behaviour": "Tabia {positive}{pos} {concern}{con}.",
        "report_status": "Hali: {icon}{risk}.",
        "risk_green": "Sawa",
        "risk_watch": "Angalia",
        "risk_at_risk": "Hatarini",
        "risk_critical": "Hatari kubwa",
        "risk_none": "Bado haijapimwa",
        "tip_attendance": "Ushauri: Muulize {first} kuhusu {day}. Tuma 2 kama karo ni changamoto.",
        "tip_behaviour": "Ushauri: Ongea na {first} kuhusu tabia darasani.",
        "tip_checkin": "Ushauri: Mazungumzo mafupi kila siku kuhusu shule humsaidia {first}.",
        "tip_praise": "Ushauri: Wiki nzuri! Mwambie {first} unajivunia.",
        "fallback_down": "chini",
        "fallback_up": "juu",
        "checkin": "Hatukumwona {name} {days}. Kila kitu kiko sawa? Jibu 1 Mgonjwa, 2 Karo, 3 Mengineyo.",
        "checkin_on_days": "{days}",
        "checkin_for_days": "kwa siku {count} za shule",
        "ack_1": "Asante. Pona haraka, {names}! Mwalimu wa darasa amejulishwa.",
        "ack_2": "Asante kwa kutujulisha. Shule itawasiliana nawe kuhusu msaada wa karo kwa {names}.",
        "ack_3": "Asante. Ujumbe wako kuhusu {names} umepelekwa kwa mwalimu. Tuma MSAADA kwa machaguo.",
        "ack_start": "Utapokea tena taarifa za BakiShule. Tuma ACHA kujiondoa.",
        "alert_at_risk": "Hatarini: {name} ({cls}). {summary}",
        "alert_parent_reply": "Jibu la mzazi: {text}",
        "teacher_parent_sick": "Mzazi anasema {name} ni mgonjwa. Tafadhali fuatilia.",
        "teacher_parent_reply": "Jibu la mzazi kuhusu {name}: {text}",
        "teacher_parent_message": "Ujumbe kutoka kwa mzazi wa {name}: {text}",
        "reward_congrats": "Hongera {first}! Umekamilisha wiki 4 bila kukosa shule. Umepata salio la KES {amount}.",
        "sponsor_receipt": "Msaada wa karo wa KES {amount} umepangwa kwa {name}.",
    },
}


def normalize_language(lang: str | None) -> str:
    return lang if lang in LANGUAGES else DEFAULT_LANGUAGE


def t(key: str, lang: str | None = None, **params) -> str:
    """Text for `key` in `lang` (en/sw; anything else falls back to English)."""
    template = MESSAGES[normalize_language(lang)][key]
    return template.format(**params) if params else template


def placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def weekday_name(weekday: int, lang: str | None, short: bool = False) -> str:
    return t("weekdays_short" if short else "weekdays", lang).split(",")[weekday]


def format_date(day: date, lang: str | None, short: bool = False) -> str:
    """'Jumatano 25 Nov' / 'Wednesday 25 Nov' (short: 'Jtn 25 Nov' / 'Wed 25 Nov')."""
    month = t("months", lang).split(",")[day.month - 1]
    return t(
        "date_short" if short else "date_long",
        lang,
        weekday=weekday_name(day.weekday(), lang, short),
        day=day.day,
        month=month,
    )


def join_list(items: list[str], lang: str | None) -> str:
    """['Jumatatu', 'Jumanne'] -> 'Jumatatu na Jumanne'."""
    if len(items) <= 1:
        return "".join(items)
    return t("list_and", lang, items=", ".join(items[:-1]), last=items[-1])


def behaviour_label(code: int, lang: str | None, short: bool = False) -> str:
    key = f"behaviour_short_{code}" if short else f"behaviour_{code}"
    return t(key, lang) if key in MESSAGES["en"] else str(code)


def subject_label(subject: str | None, lang: str | None) -> str | None:
    """Subjects are stored by their English name; translate for display."""
    if not subject:
        return None
    for key, value in MESSAGES["en"].items():
        if key.startswith("subject_") and value == subject:
            return t(key, lang)
    return subject
