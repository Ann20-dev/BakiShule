"""School-level configuration: behaviour codes, subjects, risk signal and term dates.

Edit this file to change what teachers can log over USSD.
"""
from datetime import date

# Behaviour codes for the teacher USSD menu (key = menu number). Labels in both languages
# live in app/messages.py as behaviour_<code> / behaviour_short_<code>.
BEHAVIOUR_CODES: dict[int, dict[str, str]] = {
    1: {"sentiment": "positive"},  # Participated well
    2: {"sentiment": "concern"},   # Homework not done
    3: {"sentiment": "concern"},   # Late
    4: {"sentiment": "concern"},   # Disruptive
    5: {"sentiment": "positive"},  # Helped others
    6: {"sentiment": "positive"},  # Excellent test score
}

# Optional subject picker after choosing a behaviour code (key = menu number).
# Stored in the database by these English names; display names are subject_<n> in app/messages.py.
SUBJECTS: dict[int, str] = {
    1: "Maths",
    2: "English",
    3: "Kiswahili",
    4: "Science",
    5: "Social Studies",
    6: "CRE",
}

# Repeated behaviour concerns add a small extra risk signal.
BEHAVIOUR_RISK = {"window_days": 14, "threshold": 3, "points": 8}

# Approximate Kenyan school term start dates as (month, day).
TERM_STARTS: list[tuple[int, int]] = [(1, 5), (4, 27), (8, 24)]

# Guardian PIN rules.
PIN_MAX_ATTEMPTS = 5
PIN_LOCK_MINUTES = 60


def term_start(today: date) -> date:
    starts = [date(today.year, month, day) for month, day in TERM_STARTS]
    past = [start for start in starts if start <= today]
    if past:
        return max(past)
    month, day = TERM_STARTS[-1]
    return date(today.year - 1, month, day)
