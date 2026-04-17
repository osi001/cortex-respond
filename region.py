"""Region routing: map IP -> country -> region bucket.

Three regions: london (Europe), lagos (Africa), newyork (everywhere else).
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

VALID_REGIONS = ("london", "newyork", "lagos")

# ISO-2 country code -> region slug. Unlisted countries fall through to newyork.
_EUROPE = {"GB", "IE", "FR", "DE", "ES", "IT", "NL", "BE", "PT", "CH",
           "AT", "SE", "NO", "DK", "FI", "PL", "CZ", "GR", "RO", "HU",
           "IS", "LU"}

_AFRICA = {"NG", "GH", "KE", "ZA", "EG", "MA", "TZ", "UG", "RW", "ET",
           "SN", "CI", "CM", "ZM", "ZW"}


def country_to_region(country_code: str) -> str:
    """Map ISO-2 country code to a region slug. Unknown -> newyork."""
    cc = (country_code or "").upper().strip()
    if cc in _EUROPE:
        return "london"
    if cc in _AFRICA:
        return "lagos"
    return "newyork"
