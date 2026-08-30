# Architecture

Detection is a subtraction. Everything else in this repository exists
to answer the second question: what is left after you actually trade it.

## Module map

| module | responsibility |
|---|---|
| `book.py` | order book, best quotes, walking the book, slippage |
| `arb.py` | venue fee models, Kelly, the costed arbitrage check |
| `polymarket.py` | Gamma market list and CLOB depth, cached |
| `scanner.py` | the scan, and the pair-sum distribution |
| `__main__.py` | CLI |


## Why it is shaped this way

**The book sorts on construction.** Polymarket returns asks in
descending order. Reading the raw first element quotes the *worst* offer
in the book as the best, which manufactures arbitrages that do not
exist -- a silent bug, and a flattering one.

**Kelly is implemented but not used for the riskless pair.** A guaranteed
dollar has no variance, so Kelly says stake everything. The real limit is
book depth and the capital locked up until resolution.

**No dependencies.** A tool whose claim is "this edge does not survive
costs" should not need a stack to audit.

## What would break it

- Cross-venue matching is arithmetic only, deliberately not run live:
  matching a Polymarket question to a Kalshi ticker is a semantic
  problem, and a wrong match yields a confident arbitrage between two
  different events, which is the worst possible failure.
- Resolution risk between venues is not modelled.
- No order is ever placed.

