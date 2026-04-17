import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_europe_countries_map_to_london():
    from region import country_to_region
    for cc in ["GB", "IE", "FR", "DE", "ES", "IT", "NL", "BE", "PT", "CH",
               "AT", "SE", "NO", "DK", "FI", "PL", "CZ", "GR", "RO", "HU",
               "IS", "LU"]:
        assert country_to_region(cc) == "london", f"{cc} should map to london"


def test_africa_countries_map_to_lagos():
    from region import country_to_region
    for cc in ["NG", "GH", "KE", "ZA", "EG", "MA", "TZ", "UG", "RW", "ET",
               "SN", "CI", "CM", "ZM", "ZW"]:
        assert country_to_region(cc) == "lagos", f"{cc} should map to lagos"


def test_other_countries_default_to_newyork():
    from region import country_to_region
    for cc in ["US", "CA", "MX", "BR", "JP", "IN", "AU", "AE", "XX", ""]:
        assert country_to_region(cc) == "newyork", f"{cc} should map to newyork"


def test_country_code_is_case_insensitive():
    from region import country_to_region
    assert country_to_region("gb") == "london"
    assert country_to_region("ng") == "lagos"
    assert country_to_region("us") == "newyork"
