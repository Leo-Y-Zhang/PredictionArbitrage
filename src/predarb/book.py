"""Order books, and what it actually costs to trade against one.

The detection half of an arbitrage is a subtraction. The execution half is this
file: you do not get the top-of-book price for any size beyond the top level, so
the number that matters is the average price after walking the book.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Level:
    price: float
    size: float


@dataclass
class OrderBook:
    """Bids sorted best (highest) first, asks best (lowest) first.

    Venues do not agree on ordering -- Polymarket returns asks descending, so
    the best ask is the *last* element of the raw payload. Sorting on
    construction means a caller can never accidentally quote the worst price in
    the book as the best, which is a silent and very flattering bug.
    """
    bids: list[Level] = field(default_factory=list)
    asks: list[Level] = field(default_factory=list)

    def __post_init__(self):
        self.bids = sorted(self.bids, key=lambda l: -l.price)
        self.asks = sorted(self.asks, key=lambda l: l.price)

    @classmethod
    def from_payload(cls, payload):
        def levels(rows):
            out = []
            for r in rows or []:
                price = float(r["price"])
                size = float(r["size"])
                if size > 0:
                    out.append(Level(price, size))
            return out
        return cls(bids=levels(payload.get("bids")), asks=levels(payload.get("asks")))

    @property
    def best_bid(self):
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self):
        return self.asks[0].price if self.asks else None

    @property
    def spread(self):
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def mid(self):
        if self.best_bid is None or self.best_ask is None:
            return None
        return 0.5 * (self.best_bid + self.best_ask)

    def liquidity_weighted_mid(self, depth=5):
        """Size-weighted mid over the top ``depth`` levels each side.

        A thin best quote sitting in front of size at a worse price makes the
        raw mid misleading; this is the p-bar of the brief.
        """
        rows = self.bids[:depth] + self.asks[:depth]
        total = sum(l.size for l in rows)
        if total <= 0:
            return None
        return sum(l.price * l.size for l in rows) / total

    def ask_depth(self):
        return sum(l.size for l in self.asks)

    def bid_depth(self):
        return sum(l.size for l in self.bids)

    def walk_asks(self, shares):
        """Buy ``shares`` by consuming asks. Returns (filled, cost, avg_price).

        Fills what it can and reports it, rather than pretending the book is
        deeper than it is.
        """
        remaining, cost = float(shares), 0.0
        for level in self.asks:
            if remaining <= 0:
                break
            take = min(remaining, level.size)
            cost += take * level.price
            remaining -= take
        filled = float(shares) - remaining
        avg = cost / filled if filled > 0 else float("nan")
        return filled, cost, avg

    def walk_bids(self, shares):
        """Sell ``shares`` into bids. Returns (filled, proceeds, avg_price)."""
        remaining, proceeds = float(shares), 0.0
        for level in self.bids:
            if remaining <= 0:
                break
            take = min(remaining, level.size)
            proceeds += take * level.price
            remaining -= take
        filled = float(shares) - remaining
        avg = proceeds / filled if filled > 0 else float("nan")
        return filled, proceeds, avg

    def slippage(self, shares):
        """Average fill price minus best ask, per share, when buying."""
        if self.best_ask is None:
            return float("nan")
        filled, _, avg = self.walk_asks(shares)
        if filled <= 0:
            return float("nan")
        return avg - self.best_ask

    def max_size_within(self, limit_price):
        """Shares buyable without paying more than ``limit_price`` per share."""
        return sum(l.size for l in self.asks if l.price <= limit_price)
