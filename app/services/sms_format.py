"""SMS length rules: GSM-7 vs UCS-2 encoding and segment counting.

GSM-7: 160 chars in one SMS, 153 per segment when split.
UCS-2 (any emoji such as ⭐/⚠️, or other non-GSM characters): 70 / 67 UTF-16 units.
"""
import math
import re

from app.config import settings
from app.messages import t

GSM7_BASIC = set(
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
    "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà"
)
GSM7_EXTENDED = set("^{}\\[~]|€")

MAX_SEGMENTS = 2
USSD_MAX_CHARS = 180


def is_gsm7(text: str) -> bool:
    return all(char in GSM7_BASIC or char in GSM7_EXTENDED for char in text)


def sms_units(text: str) -> tuple[str, int]:
    if is_gsm7(text):
        return "gsm7", sum(2 if char in GSM7_EXTENDED else 1 for char in text)
    return "ucs2", len(text.encode("utf-16-le")) // 2


def sms_segments(text: str) -> int:
    """Number of SMS segments AT will bill for this text (GSM-7 or UCS-2)."""
    encoding, units = sms_units(text)
    single, multi = (160, 153) if encoding == "gsm7" else (70, 67)
    if units <= single:
        return 1
    return math.ceil(units / multi)


segment_count = sms_segments  # backwards-compatible name


def plain_text(text: str, lang: str | None = None) -> str:
    """Emoji-free fallback: ⭐->*, ⚠️->!, ✅->OK, ⬇️/⬆️->down/up (translated), drop 🟢🟡🟠🔴."""
    text = text.replace("⚠️", "!").replace("⚠", "!").replace("⭐", "*").replace("✅", "OK")
    text = text.replace("⬇️", t("fallback_down", lang)).replace("⬆️", t("fallback_up", lang))
    text = re.sub(r"[🟢🟡🟠🔴]\s?", "", text)
    return text.replace("\ufe0f", "")


def fit_sms(lines: list[str], lang: str | None = None, sep: str = "\n", max_segments: int = MAX_SEGMENTS) -> str:
    """Join parts into one SMS of at most `max_segments`.

    1. With SMS_USE_EMOJI on, keep emojis if it fits.
    2. Otherwise use the plain-text fallback.
    3. If still too long, drop trailing (least important) parts, then truncate.
    """
    lines = [line for line in lines if line]
    text = sep.join(lines)
    if settings.sms_use_emoji and sms_segments(text) <= max_segments:
        return text
    lines = [plain_text(line, lang) for line in lines]
    text = sep.join(lines)
    while sms_segments(text) > max_segments and len(lines) > 1:
        lines = lines[:-1]
        text = sep.join(lines)
    if sms_segments(text) > max_segments:  # a single over-long part
        while text and sms_segments(text + "...") > max_segments:
            text = text[:-1]
        text += "..."
    return text


def fit_ussd(lines: list[str], max_chars: int = USSD_MAX_CHARS) -> str:
    lines = [line for line in lines if line]
    text = "\n".join(lines)
    while len(text) > max_chars and len(lines) > 1:
        lines = lines[:-1]
        text = "\n".join(lines)
    return text[:max_chars]
