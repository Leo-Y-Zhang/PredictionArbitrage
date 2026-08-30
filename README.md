# PredictionArbitrage

Detecting an arbitrage in a prediction market is a subtraction. If the YES and
NO asks of the same contract sum below a dollar, buying both guarantees a dollar
at resolution:

```
edge = 1 − (yes_ask + no_ask)
```

That is the easy half. This repository is mostly the other half — the fee, the
spread you cross, the slippage from walking the book for real size, and the gas
— because that is where the edge goes.

## What it found

Scanned 200 live Polymarket order books on 2026-08-30, restricted to
open binary markets with at least $500 of resting liquidity.

**Apparent arbitrages at top of book: 0. Surviving costs: 0.**

A bare zero is not worth much on its own — it looks the same whether the market
is efficient or the scanner is broken. So the scan records the whole
distribution of YES ask + NO ask, where **1.0000 is the arbitrage boundary**:

| | value |
|---|---|
| books with two-sided quotes | 140 |
| minimum pair sum | **1.0010** |
| median pair sum | **1.0010** |
| maximum pair sum | 1.0100 |
| sums below 1.0000 | **0** |
| sums within one cent of 1.0000 | 127 of 140 |

Not one book was priced through the boundary, and the median sat exactly
1.0010 — one tick above it, on a market with a 0.001 tick. The
no-arbitrage condition is not approximately enforced here, it is enforced to the
smallest increment the venue allows.

That is consistent with the published work: a 2026 UCLA study of 75 million
Polymarket order-book snapshots found seven executable single-market
arbitrages across 173 NBA games, each alive for about 3.6 seconds. Efficiency
measured rather than assumed.

## Why the cost model is the project

The scanner will happily report a gross edge. Whether that edge is real depends
on four things it also computes:

- **Walking the book.** The top-of-book price applies to the top-of-book size.
  `OrderBook.walk_asks` fills across levels and returns the average price paid,
  so a four-cent edge that is one share deep is correctly valued at almost
  nothing.
- **Fees.** Kalshi charges `ceil(0.07 · C · P · (1−P))` in cents, which peaks at
  a price of 0.50 — worst exactly where most contracts trade. Polymarket has
  charged no trading fee on most markets, kept as a parameter rather than
  hard-coded so the assumption stays visible.
- **Gas.** A fixed cost per round trip, which is what actually kills small
  arbitrages: a half-cent edge on 100 shares is 50 cents of profit.
- **Sizing.** Kelly is implemented for the risky case, `f* = (bp − q)/b`. It is
  deliberately *not* used to size the riskless pair: a guaranteed dollar has no
  variance, so Kelly says stake everything, and the real limit is book depth and
  the capital you are willing to lock up until resolution.

## Running it

Requires only the Python standard library to scan; tests need nothing extra.

```
python scan.py --limit 200            # cached books
python scan.py --limit 200 --refresh  # pull fresh books from the CLOB
python -m unittest discover -s tests -v
```

Market metadata comes from Polymarket's Gamma API and depth from the CLOB
`/book` endpoint. Both are public and unauthenticated.

## Tests

35 tests, all offline, every fixture hand-computable.

The one worth naming guards a trap: **Polymarket returns asks in descending
order**, so reading the first element as the best price quotes the *worst* offer
in the book as the best — which manufactures arbitrages that do not exist.
`OrderBook` sorts on construction and a test drives a real-shaped descending
payload through it.

Two others earn their place:

- an end-to-end test that injects an arbitrage as a raw venue payload and
  requires the pipeline to find it, so the live zero above means "efficient"
  rather than "broken"
- a test that a pair summing to 1.001 — what the live scan actually observes —
  is correctly rejected

Writing the fee tests found a real bug: `0.07 × 100 × 0.5 × 0.5` evaluates to
1.7500000000000002 in binary floating point, so taking the ceiling without
rounding first billed $1.76 for a fee that is exactly $1.75. The error was
always upward, so it silently overstated costs on every round number.

## Layout

| file | purpose |
|---|---|
| `src/predarb/book.py` | order book, best quotes, walking the book, slippage |
| `src/predarb/arb.py` | fee models, Kelly, the costed arbitrage check |
| `src/predarb/polymarket.py` | Gamma market list and CLOB depth, cached |
| `scan.py` | live scan, writes `results.json` |
| `make_readme.py` | renders this file from `results.json` |

## Limits

Single-venue only. Cross-venue edge is implemented as arithmetic
(`cross_venue_edge`) but not run live, because matching a Polymarket question to
a Kalshi ticker is a semantic problem, and a wrong match produces a confident
arbitrage between two different events — the worst possible failure. Doing it
properly needs a resolution-criteria comparison, not string similarity.

No order is ever placed. This measures what a book implies; it does not trade.

Every number above is injected from `results.json` by `make_readme.py`, which
fails if a value is missing.

## Reference

Cheng, Yang & Zou, *Arbitrage Analysis in Polymarket NBA Markets*, UCLA, 2026.
