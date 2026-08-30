"""Fees, sizing, and whether an apparent arbitrage survives execution.

The gross edge on a prediction-market arbitrage is a subtraction anyone can do.
What decides whether it is real is the stack underneath it: the fee each venue
charges, the spread you cross to get filled, the slippage from walking the book
for real size, and on-chain gas. This module is that stack.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# ---------------------------------------------------------------- fees

def kalshi_fee(price, contracts):
    """Kalshi's published trading fee: ceil(0.07 * C * P * (1-P)) in cents.

    It is largest at a price of 0.50, where P(1-P) peaks, and vanishes at the
    extremes -- so the fee is worst exactly where most contracts trade.
    """
    if contracts <= 0:
        return 0.0
    raw_cents = 0.07 * contracts * price * (1.0 - price) * 100.0
    # Round before the ceiling. 0.07 * 100 * 0.5 * 0.5 evaluates to
    # 1.7500000000000002 in binary floating point, and ceiling that without
    # rounding first bills 1.76 for a fee that is exactly 1.75. The error is
    # always upward, so it silently overstates costs on every round number.
    return math.ceil(round(raw_cents, 9)) / 100.0


def polymarket_fee(price, contracts, fee_rate=0.0):
    """Polymarket has charged no trading fee on most markets.

    Kept as a parameter rather than hard-coded to zero so a fee regime can be
    modelled, and so the assumption is visible instead of buried.
    """
    return fee_rate * contracts * price


FEE_MODELS = {"polymarket": polymarket_fee, "kalshi": kalshi_fee}


# ---------------------------------------------------------------- sizing

def kelly_fraction(p, b):
    """Kelly stake for a bet paying ``b`` to 1 with win probability ``p``.

    f* = (bp - q) / b. Negative means the bet is bad; clipped to zero.
    """
    if b <= 0:
        return 0.0
    q = 1.0 - p
    return max((b * p - q) / b, 0.0)


def kelly_for_binary_contract(price, true_prob):
    """Kelly stake for buying a contract at ``price`` that pays 1.

    Buying at price c returns (1-c)/c on a win, so b = (1 - c)/c.
    """
    if not (0.0 < price < 1.0):
        return 0.0
    return kelly_fraction(true_prob, (1.0 - price) / price)


# ---------------------------------------------------------------- arbitrage

@dataclass
class ArbResult:
    gross_edge: float          # 1 - (yes_ask + no_ask) at top of book
    net_edge: float            # after fees, slippage and gas, per contract
    shares: float              # size actually executable
    cost: float                # total outlay
    payout: float              # guaranteed return at resolution
    profit: float              # payout - cost - fees - gas
    fees: float
    gas: float
    slippage_cost: float
    executable: bool
    reason: str = ""

    def as_dict(self):
        return self.__dict__.copy()


def within_venue_arbitrage(yes_book, no_book, venue="polymarket",
                           max_shares=1000.0, gas=0.0, fee_rate=0.0,
                           min_profit=0.01):
    """Buy YES and NO of the same contract; the pair always redeems for 1.

    If both asks together cost less than 1, the difference is riskless -- before
    costs. This walks both books for the size being considered, applies the
    venue fee to each leg, adds gas once, and reports what is left.

    Sizing here is not Kelly. A riskless pair has no variance, so Kelly would
    say stake everything; the real constraint is book depth and the capital you
    are willing to lock up until resolution, which is what ``max_shares``
    represents.
    """
    ya, na = yes_book.best_ask, no_book.best_ask
    if ya is None or na is None:
        return ArbResult(float("nan"), float("nan"), 0, 0, 0, 0, 0, gas, 0,
                         False, "one side has no offers")

    gross = 1.0 - (ya + na)

    depth = min(yes_book.ask_depth(), no_book.ask_depth(), max_shares)
    if depth <= 0:
        return ArbResult(gross, float("nan"), 0, 0, 0, 0, 0, gas, 0,
                         False, "no depth")

    y_filled, y_cost, y_avg = yes_book.walk_asks(depth)
    n_filled, n_cost, n_avg = no_book.walk_asks(depth)
    shares = min(y_filled, n_filled)
    if shares <= 0:
        return ArbResult(gross, float("nan"), 0, 0, 0, 0, 0, gas, 0,
                         False, "unfillable")

    # re-walk at the common size so both legs match
    _, y_cost, y_avg = yes_book.walk_asks(shares)
    _, n_cost, n_avg = no_book.walk_asks(shares)

    fee_fn = FEE_MODELS[venue]
    if venue == "polymarket":
        fees = (fee_fn(y_avg, shares, fee_rate) + fee_fn(n_avg, shares, fee_rate))
    else:
        fees = fee_fn(y_avg, shares) + fee_fn(n_avg, shares)

    cost = y_cost + n_cost
    payout = shares * 1.0
    slip = (y_avg - ya) * shares + (n_avg - na) * shares
    profit = payout - cost - fees - gas
    net_edge = profit / shares if shares > 0 else float("nan")

    executable = profit >= min_profit
    reason = "" if executable else (
        "gross edge negative" if gross <= 0 else
        "costs exceed the edge")
    return ArbResult(gross, net_edge, shares, cost, payout, profit,
                     fees, gas, slip, executable, reason)


def cross_venue_edge(yes_price_a, no_price_b):
    """Buy YES on venue A and NO on venue B for the same event.

    The pair redeems for exactly 1 whichever way the event resolves, so the
    edge is 1 - (p_yes^A + p_no^B), same shape as the single-venue case but
    exposed to the two venues resolving differently, which is a real risk and
    not modelled here.
    """
    return 1.0 - (yes_price_a + no_price_b)
