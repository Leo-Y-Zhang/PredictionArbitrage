"""Scan live Polymarket books for YES+NO arbitrage, and cost it honestly.

Writes results.json. The interesting output is not the list of hits, it is how
many apparent edges survive fees, slippage and gas.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from predarb import polymarket                      # noqa: E402
from predarb.book import OrderBook                  # noqa: E402
from predarb.arb import within_venue_arbitrage      # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--min-liquidity", type=float, default=500.0)
    ap.add_argument("--max-shares", type=float, default=1000.0)
    ap.add_argument("--gas", type=float, default=0.02,
                    help="on-chain cost per round trip in dollars")
    ap.add_argument("--fee-rate", type=float, default=0.0,
                    help="Polymarket taker fee; zero on most markets")
    ap.add_argument("--min-profit", type=float, default=0.01)
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    markets = polymarket.active_markets(args.limit, args.min_liquidity,
                                        use_cache=not args.refresh)
    print(f"markets with two outcomes and liquidity >= "
          f"${args.min_liquidity:,.0f}: {len(markets)}")

    gross_hits, net_hits, rows, scanned, failed = 0, 0, [], 0, 0
    sums = []   # yes_ask + no_ask per market: the whole distribution,
                # so a null result is a measurement of efficiency rather
                # than an absence of evidence
    for i, m in enumerate(markets, 1):
        try:
            yb = OrderBook.from_payload(
                polymarket.order_book(m["token_ids"][0], use_cache=not args.refresh))
            nb = OrderBook.from_payload(
                polymarket.order_book(m["token_ids"][1], use_cache=not args.refresh))
        except Exception:
            failed += 1
            continue
        scanned += 1

        if yb.best_ask is not None and nb.best_ask is not None:
            sums.append(yb.best_ask + nb.best_ask)

        r = within_venue_arbitrage(yb, nb, venue="polymarket",
                                   max_shares=args.max_shares, gas=args.gas,
                                   fee_rate=args.fee_rate,
                                   min_profit=args.min_profit)
        if r.gross_edge is not None and r.gross_edge > 0:
            gross_hits += 1
            if r.executable:
                net_hits += 1
            rows.append({"question": m["question"],
                         "condition_id": m["condition_id"],
                         "liquidity": m["liquidity"],
                         "best_yes_ask": yb.best_ask,
                         "best_no_ask": nb.best_ask,
                         **r.as_dict()})
        if i % 50 == 0:
            print(f"  {i}/{len(markets)} scanned, {gross_hits} gross, "
                  f"{net_hits} survive costs")

    import statistics
    sums_sorted = sorted(sums)
    stats = None
    if sums_sorted:
        stats = {
            "n": len(sums_sorted),
            "min": sums_sorted[0],
            "p05": sums_sorted[max(0, int(0.05 * len(sums_sorted)) - 1)],
            "median": statistics.median(sums_sorted),
            "mean": statistics.fmean(sums_sorted),
            "max": sums_sorted[-1],
            "n_below_1": sum(1 for v in sums_sorted if v < 1.0),
            "n_within_1c_of_1": sum(1 for v in sums_sorted if abs(v - 1.0) <= 0.01),
            "n_within_2c_of_1": sum(1 for v in sums_sorted if abs(v - 1.0) <= 0.02),
        }

    rows.sort(key=lambda r: -r["profit"])
    out = {
        "asof": dt.datetime.now().isoformat(timespec="seconds"),
        "venue": "polymarket",
        "params": vars(args),
        "n_markets": len(markets),
        "n_scanned": scanned,
        "n_book_failures": failed,
        "n_gross_edges": gross_hits,
        "n_executable": net_hits,
        "survival_rate": (net_hits / gross_hits) if gross_hits else None,
        "pair_sum_distribution": stats,
        "opportunities": rows[:50],
    }
    with open("results.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1)

    print(f"\nscanned {scanned} books ({failed} failed to load)")
    print(f"apparent edges at top of book : {gross_hits}")
    print(f"survive fees, slippage and gas: {net_hits}")
    if gross_hits:
        print(f"survival rate                 : {net_hits / gross_hits:.1%}")
    if stats:
        print(f"\nYES ask + NO ask across {stats['n']} books "
              f"(1.0000 is the arbitrage boundary):")
        print(f"  min {stats['min']:.4f}   5th pct {stats['p05']:.4f}   "
              f"median {stats['median']:.4f}   max {stats['max']:.4f}")
        print(f"  below 1.0000: {stats['n_below_1']}   "
              f"within 1 cent: {stats['n_within_1c_of_1']}   "
              f"within 2 cents: {stats['n_within_2c_of_1']}")
    for r in rows[:8]:
        tag = "EXECUTABLE" if r["executable"] else f"dies: {r['reason']}"
        print(f"  {r['gross_edge']:+.4f} gross -> {r['profit']:+8.2f} USD  "
              f"[{tag}]  {str(r['question'])[:58]}")


if __name__ == "__main__":
    main()
