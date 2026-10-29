# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""Validate binary-market metadata and cached JSON without contacting a venue."""
import io
import json
from urllib.parse import parse_qs, urlparse

import pytest

from predarb import polymarket


def market(**changes):
    return {
        "question": "fixture", "conditionId": "pair",
        "clobTokenIds": '["yes", "no"]', "outcomes": '["Yes", "No"]',
        "liquidityNum": "500", "volumeNum": "12", "endDate": "2030-01-01",
        "negRisk": False, **changes,
    }


@pytest.fixture
def cache(tmp_path, monkeypatch):
    monkeypatch.setattr(polymarket, "CACHE_DIR", str(tmp_path))
    return tmp_path


def test_binary_market_at_liquidity_threshold_is_accepted(cache, monkeypatch):
    urls = []

    def get(url):
        urls.append(url)
        return [market()]

    monkeypatch.setattr(polymarket, "_get", get)
    result = polymarket.active_markets(limit=10, min_liquidity=500)
    assert result == [{
        "question": "fixture", "condition_id": "pair", "outcomes": ["Yes", "No"],
        "token_ids": ["yes", "no"], "liquidity": 500.0, "volume": 12.0,
        "end_date": "2030-01-01", "neg_risk": False,
    }]
    assert parse_qs(urlparse(urls[0]).query) == {
        "limit": ["10"], "offset": ["0"], "closed": ["false"],
        "active": ["true"], "order": ["liquidityNum"], "ascending": ["false"],
    }
    assert json.loads((cache / "markets_10_500.json").read_text()) == result


@pytest.mark.parametrize("changes", [
    {"clobTokenIds": "[]"},
    {"clobTokenIds": '["yes"]'},
    {"clobTokenIds": '["yes", "no", "other"]'},
    {"outcomes": "[]"},
    {"outcomes": '["Yes"]'},
    {"outcomes": '["Yes", "No", "Other"]'},
    {"clobTokenIds": '["yes",'},
    {"outcomes": '["Yes",'},
    {"clobTokenIds": ["yes", "no"]},
    {"liquidityNum": "499.99"},
    {"liquidityNum": None},
])
def test_corrupted_or_illiquid_market_is_filtered(cache, monkeypatch, changes):
    # Retain a valid control beside each corruption so dropping everything fails.
    monkeypatch.setattr(polymarket, "_get", lambda url: [market(), market(**changes)])
    result = polymarket.active_markets(limit=10, min_liquidity=500, use_cache=False)
    assert len(result) == 1
    assert result[0]["token_ids"] == ["yes", "no"]
    assert result[0]["outcomes"] == ["Yes", "No"]


def test_market_cache_can_be_read_and_explicitly_refreshed(cache, monkeypatch):
    calls = []

    def get(url):
        calls.append(url)
        return [market(question=f"version {len(calls)}")]

    monkeypatch.setattr(polymarket, "_get", get)
    first = polymarket.active_markets(limit=10)
    assert polymarket.active_markets(limit=10) == first
    assert len(calls) == 1
    fresh = polymarket.active_markets(limit=10, use_cache=False)
    assert fresh[0]["question"] == "version 2"
    assert polymarket.active_markets(limit=10) == fresh
    assert len(calls) == 2


def test_book_cache_keys_and_refresh_preserve_the_payload(cache, monkeypatch):
    calls = []

    def get(url):
        calls.append(url)
        return {"asks": [{"price": "0.4", "size": str(len(calls))}]}

    monkeypatch.setattr(polymarket, "_get", get)
    first_token, second_token = "t" * 23 + "a", "t" * 23 + "b"
    first = polymarket.order_book(first_token)
    assert polymarket.order_book(first_token) == first
    second = polymarket.order_book(second_token)
    assert second != first
    fresh = polymarket.order_book(first_token, use_cache=False)
    assert fresh != first
    assert polymarket.order_book(first_token) == fresh
    assert len(calls) == 3
    assert parse_qs(urlparse(calls[0]).query) == {"token_id": [first_token]}
    assert json.loads((cache / f"book_{first_token}.json").read_text()) == fresh


@pytest.mark.parametrize("kind", ["markets", "book"])
def test_truncated_cache_is_rejected(cache, monkeypatch, kind):
    monkeypatch.setattr(polymarket, "_get", lambda url: pytest.fail("cache must be read"))
    if kind == "markets":
        path = cache / "markets_10_500.json"
        path.write_text('[{"token_ids": ["yes", "no"]}]')
        assert polymarket.active_markets(limit=10) == [{"token_ids": ["yes", "no"]}]
        path.write_text('[{"token_ids": ["yes",')
        with pytest.raises(json.JSONDecodeError):
            polymarket.active_markets(limit=10)
    else:
        path = cache / "book_yes.json"
        path.write_text('{"asks": []}')
        assert polymarket.order_book("yes") == {"asks": []}
        path.write_text('{"asks": [')
        with pytest.raises(json.JSONDecodeError):
            polymarket.order_book("yes")


def test_get_decodes_json_and_rejects_truncated_responses(monkeypatch):
    payload = b'{"asks": []}'
    calls, sleeps = [], []

    def urlopen(request, timeout):
        calls.append((request.full_url, timeout))
        return io.BytesIO(payload)

    monkeypatch.setattr(polymarket.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(polymarket.time, "sleep", sleeps.append)
    assert polymarket._get("https://example.invalid/book", timeout=2) == {"asks": []}
    payload = b'{"asks": ['
    with pytest.raises(RuntimeError, match="GET failed after 2 tries"):
        polymarket._get("https://example.invalid/book", timeout=2, retries=2)
    assert calls == [("https://example.invalid/book", 2)] * 3
    assert sleeps == [1.5, 3.0]
