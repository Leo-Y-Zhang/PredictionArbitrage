# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""Scan live books and cost every apparent arbitrage.

The output that matters is not the list of hits. It is the distribution of
YES ask + NO ask across every book, because a bare count of zero looks
identical whether the market is efficient or the scanner is broken.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics

from . import polymarket
from .arb import within_venue_arbitrage
from .book import OrderBook


def pair_sum_stats(sums: list[float]) -> dict | None:
    """Where the market sits relative to the 1.0000 arbitrage boundary."""
    if not sums:
        return None
    s = sorted(sums)
    return {
        "n": len(s), "min": s[0], "max": s[-1],
        "p05": s[max(0, int(0.05 * len(s)) - 1)],
        "median": statistics.median(s), "mean": statistics.fmean(s),
        "n_below_1": sum(1 for v in s if v < 1.0),
        "n_within_1c_of_1": sum(1 for v in s if abs(v - 1.0) <= 0.01),
        "n_within_2c_of_1": sum(1 for v in s if abs(v - 1.0) <= 0.02),
    }


def run(limit=300, min_liquidity=500.0, max_shares=1000.0, gas=0.02,
        fee_rate=0.0, min_profit=0.01, refresh=False, quiet=False,
        out_path="results.json"):
    say = (lambda *a: None) if quiet else print
    markets = polymarket.active_markets(limit, min_liquidity, use_cache=not refresh)
    say(f"markets with two outcomes and liquidity >= ${min_liquidity:,.0f}: "
        f"{len(markets)}")

    gross_hits = net_hits = scanned = failed = 0
    rows: list[dict] = []
    sums: list[float] = []

    for i, m in enumerate(markets, 1):
        try:
            yb = OrderBook.from_payload(
                polymarket.order_book(m["token_ids"][0], use_cache=not refresh))
            nb = OrderBook.from_payload(
                polymarket.order_book(m["token_ids"][1], use_cache=not refresh))
        except Exception:
            failed += 1
            continue
        scanned += 1
        if yb.best_ask is not None and nb.best_ask is not None:
            sums.append(yb.best_ask + nb.best_ask)

        r = within_venue_arbitrage(yb, nb, venue="polymarket",
                                   max_shares=max_shares, gas=gas,
                                   fee_rate=fee_rate, min_profit=min_profit)
        if r.gross_edge is not None and r.gross_edge > 0:
            gross_hits += 1
            if r.executable:
                net_hits += 1
            rows.append({"question": m["question"],
                         "condition_id": m["condition_id"],
                         "liquidity": m["liquidity"],
                         "best_yes_ask": yb.best_ask,
                         "best_no_ask": nb.best_ask, **r.as_dict()})
        if i % 50 == 0:
            say(f"  {i}/{len(markets)} scanned, {gross_hits} gross, "
                f"{net_hits} survive costs")

    rows.sort(key=lambda r: -r["profit"])
    stats = pair_sum_stats(sums)
    out = {
        "asof": dt.datetime.now().isoformat(timespec="seconds"),
        "venue": "polymarket",
        "params": {"limit": limit, "min_liquidity": min_liquidity,
                   "max_shares": max_shares, "gas": gas, "fee_rate": fee_rate,
                   "min_profit": min_profit},
        "n_markets": len(markets), "n_scanned": scanned,
        "n_book_failures": failed, "n_gross_edges": gross_hits,
        "n_executable": net_hits,
        "survival_rate": (net_hits / gross_hits) if gross_hits else None,
        "pair_sum_distribution": stats, "opportunities": rows[:50],
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)

    say(f"\nscanned {scanned} books ({failed} failed to load)")
    say(f"apparent edges at top of book : {gross_hits}")
    say(f"survive fees, slippage and gas: {net_hits}")
    if gross_hits:
        say(f"survival rate                 : {net_hits / gross_hits:.1%}")
    if stats:
        say(f"\nYES ask + NO ask across {stats['n']} books "
            f"(1.0000 is the arbitrage boundary):")
        say(f"  min {stats['min']:.4f}   5th pct {stats['p05']:.4f}   "
            f"median {stats['median']:.4f}   max {stats['max']:.4f}")
        say(f"  below 1.0000: {stats['n_below_1']}   "
            f"within 1 cent: {stats['n_within_1c_of_1']}   "
            f"within 2 cents: {stats['n_within_2c_of_1']}")
    for r in rows[:8]:
        tag = "EXECUTABLE" if r["executable"] else f"dies: {r['reason']}"
        say(f"  {r['gross_edge']:+.4f} gross -> {r['profit']:+8.2f} USD  "
            f"[{tag}]  {str(r['question'])[:58]}")
    return out
