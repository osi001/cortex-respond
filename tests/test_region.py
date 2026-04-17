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


from unittest.mock import patch, MagicMock


def test_resolve_region_with_valid_override():
    from region import resolve_region
    assert resolve_region("8.8.8.8", override="london") == "london"
    assert resolve_region("8.8.8.8", override="lagos") == "lagos"
    assert resolve_region("8.8.8.8", override="newyork") == "newyork"


def test_resolve_region_ignores_invalid_override():
    from region import resolve_region, _cache_clear
    _cache_clear()
    fake_response = MagicMock()
    fake_response.json.return_value = {"countryCode": "US"}
    fake_response.raise_for_status = MagicMock()
    with patch("region.requests.get", return_value=fake_response) as mocked:
        assert resolve_region("8.8.8.8", override="mars") == "newyork"
        mocked.assert_called_once()


def test_resolve_region_private_ip_defaults_to_lagos():
    from region import resolve_region
    assert resolve_region("127.0.0.1") == "lagos"
    assert resolve_region("192.168.1.5") == "lagos"
    assert resolve_region("10.0.0.1") == "lagos"
    assert resolve_region("") == "lagos"
    assert resolve_region(None) == "lagos"


def test_resolve_region_uses_ip_api():
    from region import resolve_region, _cache_clear
    _cache_clear()
    fake_response = MagicMock()
    fake_response.json.return_value = {"countryCode": "GB"}
    fake_response.raise_for_status = MagicMock()
    with patch("region.requests.get", return_value=fake_response) as mocked:
        assert resolve_region("81.2.69.142") == "london"
        mocked.assert_called_once()
        url = mocked.call_args[0][0]
        assert "81.2.69.142" in url
        assert "countryCode" in url


def test_resolve_region_timeout_defaults_to_newyork():
    from region import resolve_region, _cache_clear
    import requests as _r
    _cache_clear()
    with patch("region.requests.get", side_effect=_r.exceptions.Timeout):
        assert resolve_region("8.8.8.8") == "newyork"


def test_resolve_region_caches_results():
    from region import resolve_region, _cache_clear
    _cache_clear()
    fake_response = MagicMock()
    fake_response.json.return_value = {"countryCode": "NG"}
    fake_response.raise_for_status = MagicMock()
    with patch("region.requests.get", return_value=fake_response) as mocked:
        resolve_region("41.58.1.1")
        resolve_region("41.58.1.1")
        resolve_region("41.58.1.1")
        assert mocked.call_count == 1


def test_load_region_config_lagos_realestate():
    from region import load_region_config
    cfg = load_region_config("lagos", "realestate")
    assert cfg["business"]["name"] == "Apex Properties"
    assert cfg["region"]["city"] == "Lagos"
    assert cfg["region"]["currency_symbol"] == "₦"
    assert "Lekki" in cfg["region"]["example_areas"]


def test_load_region_config_lagos_dental():
    from region import load_region_config
    cfg = load_region_config("lagos", "dental")
    assert cfg["business"]["name"] == "SmileCraft Dental"
    assert cfg["region"]["currency_code"] == "NGN"


def test_load_region_config_missing_file_raises():
    from region import load_region_config
    import pytest as _pt
    with _pt.raises(FileNotFoundError):
        load_region_config("london", "realestate")  # not yet created
