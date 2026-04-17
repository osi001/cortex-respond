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


import ipaddress

import requests

IP_API_URL = "http://ip-api.com/json/{ip}?fields=countryCode"
_REQUEST_TIMEOUT_S = 2.0


def _is_private_or_empty(ip: Optional[str]) -> bool:
    if not ip:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return addr.is_private or addr.is_loopback or addr.is_link_local


@lru_cache(maxsize=1000)
def _lookup_country(ip: str) -> str:
    """Hit ip-api.com for the country code. Returns '' on any error."""
    try:
        resp = requests.get(IP_API_URL.format(ip=ip), timeout=_REQUEST_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json().get("countryCode", "") or ""
    except Exception as e:
        logger.warning("ip-api lookup failed for %s: %s", ip, e)
        return ""


def _cache_clear() -> None:
    """Test helper - clears the LRU cache."""
    _lookup_country.cache_clear()


def resolve_region(ip: Optional[str], override: Optional[str] = None) -> str:
    """
    Resolve the region for a request.

    - Valid `override` wins (one of VALID_REGIONS).
    - Private/localhost/empty IP -> 'lagos' (local dev).
    - Otherwise: ip-api.com lookup -> country_to_region. Failures -> 'newyork'.
    """
    if override in VALID_REGIONS:
        return override

    if _is_private_or_empty(ip):
        return "lagos"

    country = _lookup_country(ip)
    if not country:
        return "newyork"
    return country_to_region(country)


from pathlib import Path
import yaml

_CONFIGS_DIR = Path(__file__).parent / "configs"


def load_region_config(region: str, business_type: str) -> dict:
    """Load the YAML config for a given region + business type."""
    path = _CONFIGS_DIR / region / f"{business_type}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"No config at {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)
