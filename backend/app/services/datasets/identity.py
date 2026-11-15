"""Fictional identity generator (SPEC section 10.2, demo subset).

Every identity is a random combination of name and place pools from
assets/name_pools/nepal.yaml, with internally consistent values (the B.S. date of birth
is converted from the A.D. date with the nepali_datetime library, the English name is
the transliteration of the Nepali name, the email is built from the name). Nothing
describes a real person.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path
from typing import Any

import nepali_datetime as nd
import numpy as np
import yaml

POOLS = Path(__file__).resolve().parents[4] / "assets" / "name_pools" / "nepal.yaml"
DEV_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")


@lru_cache
def pools() -> dict[str, Any]:
    return yaml.safe_load(POOLS.read_text(encoding="utf-8"))


def _pick(rng: np.random.Generator, items: list) -> Any:
    return items[int(rng.integers(0, len(items)))]


def _person(rng: np.random.Generator, gender: str, family: dict) -> dict[str, str]:
    p = pools()
    given = _pick(rng, p["given_male"] if gender == "male" else p["given_female"])
    return {"ne": f"{given['ne']} {family['ne']}", "en": f"{given['en']} {family['en']}"}


def _address(rng: np.random.Generator) -> dict[str, dict[str, str]]:
    p = pools()
    prov = _pick(rng, p["provinces"])
    dist = _pick(rng, prov["districts"])
    mun = _pick(rng, p["municipalities"])
    tole = _pick(rng, p["toles"])
    ward = str(int(rng.integers(1, 33)))
    house = str(int(rng.integers(1, 999)))
    return {
        "country": {"ne": "नेपाल", "en": "Nepal"},
        "province": {"ne": prov["ne"], "en": prov["en"]},
        "district": {"ne": dist["ne"], "en": dist["en"]},
        "municipality": {"ne": f"{dist['ne']} {mun['ne']}", "en": f"{dist['en']} {mun['en']}"},
        "ward": {"ne": ward.translate(DEV_DIGITS), "en": ward},
        "tole": {"ne": tole["ne"], "en": tole["en"]},
        "house_no": {"ne": house.translate(DEV_DIGITS), "en": house},
    }


def make_identity(rng: np.random.Generator, ident_id: str) -> dict[str, Any]:
    p = pools()
    gender = str(rng.choice(["male", "female"]))
    fam = _pick(rng, p["family"])
    me = _person(rng, gender, fam)
    dob_ad = dt.date(1960, 1, 1) + dt.timedelta(days=int(rng.integers(0, 365 * 44)))
    dob_bs = nd.date.from_datetime_date(dob_ad)
    married = bool(rng.random() < 0.6)
    perm = _address(rng)
    cur = perm if rng.random() < 0.5 else _address(rng)
    cit_issue_ad = dob_ad + dt.timedelta(days=365 * 16 + int(rng.integers(0, 3000)))
    cit_issue_bs = nd.date.from_datetime_date(cit_issue_ad)
    first, last = me["en"].split()[0].lower(), me["en"].split()[-1].lower()
    occ = _pick(rng, p["occupations"])
    return {
        "identity_id": ident_id,
        "synthetic": True,
        "gender": gender,
        "marital_status": "married" if married else "unmarried",
        "name": me,
        "dob_ad": dob_ad.strftime("%d%m%Y"),
        "dob_bs": f"{dob_bs.day:02d}{dob_bs.month:02d}{dob_bs.year}",
        "nationality": {"ne": "नेपाली", "en": "Nepali"},
        "citizenship_number": f"{int(rng.integers(10, 77))}-{int(rng.integers(1, 99)):02d}-{int(rng.integers(100, 99999))}",
        "citizenship_issue_date": f"{cit_issue_bs.year}/{cit_issue_bs.month:02d}/{cit_issue_bs.day:02d}",
        "citizenship_issue_district": perm["district"],
        "pan_number": str(int(rng.integers(100000000, 999999999))),
        "national_id_number": "".join(str(int(d)) for d in rng.integers(0, 10, 10)),
        "passport_number": f"PA{int(rng.integers(1000000, 9999999))}" if rng.random() < 0.4 else "",
        "mobile": "98" + "".join(str(int(d)) for d in rng.integers(0, 10, 8)),
        "phone": "01-" + "".join(str(int(d)) for d in rng.integers(0, 10, 7)) if rng.random() < 0.5 else "",
        "email": f"{first}.{last}{int(rng.integers(1, 99))}@{_pick(rng, p['email_domains'])}",
        "address": {"permanent": perm, "current": cur},
        "family": {
            "father": _person(rng, "male", fam),
            "mother": _person(rng, "female", _pick(rng, p["family"])),
            "grandfather": _person(rng, "male", fam),
            "spouse": _person(rng, "female" if gender == "male" else "male", _pick(rng, p["family"])) if married else None,
        },
        "occupation": occ,
        "employer": _pick(rng, p["employers"]),
        "designation": _pick(rng, p["designations"]),
        "annual_income": str(int(rng.integers(3, 40)) * 50000),
        "education": str(rng.choice(["SLC", "+2", "Bachelor", "Master"])),
    }
