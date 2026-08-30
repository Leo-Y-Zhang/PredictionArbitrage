# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""PredictionArbitrage CLI.

  predarb scan [--limit 300] [--min-liquidity 500] [--gas 0.02] [--refresh]
      Scan live Polymarket books for YES+NO pairs summing below a dollar, cost
      each one through fees, book-walking and gas, and report how many survive.
      Also prints the distribution of pair sums, which is the part worth
      reading: a bare count of zero cannot tell you whether the market is
      efficient or the scanner is broken.

  predarb book TOKEN_ID
      Print one order book as the scanner sees it, best price first. Use this
      when a market looks mispriced: Polymarket returns asks in descending
      order, and reading the raw first element quotes the worst offer in the
      book as the best.

  predarb price YES_ASK NO_ASK [--shares N] [--venue polymarket|kalshi] [--gas G]
      Cost a hypothetical pair by hand, with no network. Shows the gross edge,
      the fee, the gas, and what is actually left. Useful for sanity-checking
      an edge someone has quoted at you.

  predarb verify
      Run the offline suite. Every fixture is hand-computable, and one test
      injects an arbitrage as a raw venue payload so that a live result of zero
      means "efficient" rather than "broken".

No order is ever placed. This measures what a book implies; it does not trade.
"""
from __future__ import annotations

import argparse
import sys


def cmd_scan(args) -> int:
    from .scanner import run
    run(limit=args.limit, min_liquidity=args.min_liquidity,
        max_shares=args.max_shares, gas=args.gas, fee_rate=args.fee_rate,
        min_profit=args.min_profit, refresh=args.refresh)
    return 0


def cmd_book(args) -> int:
    from . import polymarket
    from .book import OrderBook
    b = OrderBook.from_payload(polymarket.order_book(args.token_id,
                                                     use_cache=not args.refresh))
    print(f"best bid {b.best_bid}   best ask {b.best_ask}   "
          f"spread {b.spread}   liquidity-weighted mid "
          f"{b.liquidity_weighted_mid()}")
    print(f"\n{'asks (best first)':>26}      {'bids (best first)':>26}")
    for i in range(min(12, max(len(b.asks), len(b.bids)))):
        a = f"{b.asks[i].price:>10.4f} x {b.asks[i].size:>11,.1f}" if i < len(b.asks) else " " * 24
        d = f"{b.bids[i].price:>10.4f} x {b.bids[i].size:>11,.1f}" if i < len(b.bids) else ""
        print(f"{a}      {d}")
    print(f"\ndepth: {b.ask_depth():,.0f} offered / {b.bid_depth():,.0f} bid")
    return 0


def cmd_price(args) -> int:
    from .arb import within_venue_arbitrage
    from .book import Level, OrderBook
    yes = OrderBook(asks=[Level(args.yes_ask, args.shares)])
    no = OrderBook(asks=[Level(args.no_ask, args.shares)])
    r = within_venue_arbitrage(yes, no, venue=args.venue, max_shares=args.shares,
                               gas=args.gas, fee_rate=args.fee_rate)
    print(f"pair cost        {args.yes_ask + args.no_ask:.4f} per contract")
    print(f"gross edge       {r.gross_edge:+.4f} per contract")
    print(f"size             {r.shares:,.0f} contracts")
    print(f"outlay           {r.cost:,.2f}")
    print(f"payout at expiry {r.payout:,.2f}")
    print(f"fees             {r.fees:,.2f}   gas {r.gas:,.2f}")
    print(f"profit           {r.profit:+,.2f}")
    print(f"verdict          {'EXECUTABLE' if r.executable else 'dies: ' + (r.reason or 'no edge')}")
    return 0 if r.executable else 1


def cmd_verify(args) -> int:
    import unittest
    suite = unittest.TestLoader().discover("tests")
    ok = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite)
    return 0 if ok.wasSuccessful() else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="predarb", description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    sub = p.add_subparsers(dest="command")

    s = sub.add_parser("scan", help="scan live books for surviving arbitrage")
    s.add_argument("--limit", type=int, default=300)
    s.add_argument("--min-liquidity", type=float, default=500.0)
    s.add_argument("--max-shares", type=float, default=1000.0)
    s.add_argument("--gas", type=float, default=0.02,
                   help="on-chain cost per round trip, in dollars")
    s.add_argument("--fee-rate", type=float, default=0.0,
                   help="Polymarket taker fee; zero on most markets")
    s.add_argument("--min-profit", type=float, default=0.01)
    s.add_argument("--refresh", action="store_true")
    s.set_defaults(func=cmd_scan)

    b = sub.add_parser("book", help="print one order book, best price first")
    b.add_argument("token_id")
    b.add_argument("--refresh", action="store_true")
    b.set_defaults(func=cmd_book)

    c = sub.add_parser("price", help="cost a hypothetical pair, offline")
    c.add_argument("yes_ask", type=float)
    c.add_argument("no_ask", type=float)
    c.add_argument("--shares", type=float, default=1000.0)
    c.add_argument("--venue", choices=("polymarket", "kalshi"), default="polymarket")
    c.add_argument("--gas", type=float, default=0.02)
    c.add_argument("--fee-rate", type=float, default=0.0)
    c.set_defaults(func=cmd_price)

    v = sub.add_parser("verify", help="run the offline suite")
    v.add_argument("--verbose", action="store_true")
    v.set_defaults(func=cmd_verify)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
