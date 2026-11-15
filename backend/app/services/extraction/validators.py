"""Normalisation and validation of OCR output (SPEC section 12.6, demo subset).

Raw OCR text is always kept; `normalise` returns a cleaned value and `validate` returns a
list of human-readable problems. Ambiguous values are never silently "fixed".
"""
from __future__ import annotations

import re

DEV_TO_ASCII = str.maketrans("०१२३४५६७८९", "0123456789")
NUMERIC_RULES = {"phone_mobile", "phone_landline", "phone_any", "pan", "national_id", "ward", "amount",
                 "date_bs", "date_ad", "date_any", "account_number", "citizenship_number"}


def normalise(raw: str, rule: str) -> str:
    v = " ".join((raw or "").split())
    if rule in NUMERIC_RULES:
        v = v.translate(DEV_TO_ASCII)
    if rule in ("phone_mobile", "pan", "national_id", "ward", "amount", "account_number"):
        v = re.sub(r"[^0-9]", "", v.replace("O", "0").replace("o", "0"))
    if rule in ("date_bs", "date_ad"):
        v = re.sub(r"[^0-9]", "", v)
    if rule == "email":
        v = v.replace(" ", "").lower()
    return v


def validate(value: str, rule: str) -> list[str]:
    if not value:
        return []
    msgs: list[str] = []
    if rule == "phone_mobile" and not re.fullmatch(r"9[678]\d{8}", value):
        msgs.append("Mobile number should be 10 digits starting with 96, 97 or 98.")
    elif rule == "pan" and not re.fullmatch(r"\d{9}", value):
        msgs.append("PAN should be 9 digits.")
    elif rule == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", value):
        msgs.append("Not a valid email address.")
    elif rule in ("date_bs", "date_ad"):
        if not re.fullmatch(r"\d{8}", value):
            msgs.append("Date should have 8 digits (DDMMYYYY).")
        else:
            d, m, y = int(value[:2]), int(value[2:4]), int(value[4:])
            lo, hi = (1990, 2090) if rule == "date_bs" else (1930, 2035)
            if not (1 <= d <= 32 and 1 <= m <= 12 and lo <= y <= hi):
                msgs.append(f"Date looks out of range for {'B.S.' if rule == 'date_bs' else 'A.D.'}.")
    elif rule == "ward" and value and not (1 <= int(value) <= 40):
        msgs.append("Ward number should be between 1 and 40.")
    elif rule == "citizenship_number" and not re.search(r"\d", value):
        msgs.append("Citizenship number should contain digits.")
    return msgs
