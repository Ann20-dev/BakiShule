def normalize_number(number: str) -> str:
    """Normalize a Kenyan phone number to E.164 (+254...)."""
    number = (number or "").strip().replace(" ", "").replace("-", "")
    if not number:
        return number
    if number.startswith("+"):
        return number
    if number.startswith("00"):
        return "+" + number[2:]
    if number.startswith("254"):
        return "+" + number
    if number.startswith("0"):
        return "+254" + number[1:]
    return "+" + number
