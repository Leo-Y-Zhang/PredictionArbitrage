# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""Polymarket data access: market list from Gamma, order books from the CLOB."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

GAMMA = "https://gamma-api.polymarket.com/markets"
CLOB_BOOK = "https://clob.polymarket.com/book"
UA = {"User-Agent": "predarb/0.1 (research)"}

CACHE_DIR = os.environ.get(
    "PREDARB_CACHE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "cache"))


def _get(url, timeout=45, retries=3):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET failed after {retries} tries: {url} ({last})")


def active_markets(limit=500, min_liquidity=500.0, use_cache=True):
    """Binary markets that are open and have some resting liquidity.

    Markets with no liquidity show absurd top-of-book prices and would dominate
    any arbitrage scan with quotes nobody can trade against.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"markets_{limit}_{int(min_liquidity)}.json")
    if use_cache and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    out, offset = [], 0
    while len(out) < limit:
        q = urllib.parse.urlencode({
            "limit": min(100, limit - len(out)), "offset": offset,
            "closed": "false", "active": "true",
            "order": "liquidityNum", "ascending": "false"})
        batch = _get(f"{GAMMA}?{q}")
        if not batch:
            break
        for m in batch:
            try:
                tokens = json.loads(m.get("clobTokenIds") or "[]")
                outcomes = json.loads(m.get("outcomes") or "[]")
            except (TypeError, json.JSONDecodeError):
                continue
            if len(tokens) != 2 or len(outcomes) != 2:
                continue
            if float(m.get("liquidityNum") or 0) < min_liquidity:
                continue
            out.append({
                "question": m.get("question"),
                "condition_id": m.get("conditionId"),
                "outcomes": outcomes,
                "token_ids": tokens,
                "liquidity": float(m.get("liquidityNum") or 0),
                "volume": float(m.get("volumeNum") or 0),
                "end_date": m.get("endDate"),
                "neg_risk": bool(m.get("negRisk")),
            })
        offset += len(batch)
        if len(batch) < 100:
            break

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh)
    return out


def order_book(token_id, use_cache=True):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"book_{token_id[:24]}.json")
    if use_cache and os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    data = _get(f"{CLOB_BOOK}?token_id={token_id}")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    return data
