# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""An executable verdict must survive both input changes and execution costs."""
import math

import pytest

from predarb.arb import (
    kalshi_fee,
    kelly_for_binary_contract,
    kelly_fraction,
    within_venue_arbitrage,
)
from predarb.book import Level, OrderBook


def offers(*levels):
    return OrderBook(asks=[Level(price, size) for price, size in levels])


def test_walked_pair_accounts_for_every_cost_and_the_cap():
    result = within_venue_arbitrage(
        offers((0.4, 2), (0.45, 3)), offers((0.5, 10)),
        max_shares=4, gas=0.02, fee_rate=0.02,
    )
    assert result.executable
    assert result.reason == ""
    assert result.shares == 4
    assert result.cost == pytest.approx(3.7)
    assert result.payout == 4
    assert result.fees == pytest.approx(0.074)
    assert result.gas == 0.02
    assert result.profit == pytest.approx(0.206)
    assert result.net_edge == pytest.approx(0.0515)
    assert result.slippage_cost == pytest.approx(0.1)


@pytest.mark.parametrize("corruption", ["price", "missing_yes", "missing_no", "zero_size", "negative_size"])
def test_raw_pair_is_accepted_then_corruption_is_rejected(corruption):
    yes = {"asks": [{"price": "0.4", "size": "4"}]}
    no = {"asks": [{"price": "0.5", "size": "4"}]}
    assert within_venue_arbitrage(
        OrderBook.from_payload(yes), OrderBook.from_payload(no), max_shares=4,
    ).executable
    if corruption == "price":
        yes["asks"][0]["price"] = "0.6"
    elif corruption == "missing_yes":
        yes["asks"] = []
    elif corruption == "missing_no":
        no["asks"] = []
    else:
        yes["asks"][0]["size"] = "0" if corruption == "zero_size" else "-4"
    result = within_venue_arbitrage(
        OrderBook.from_payload(yes), OrderBook.from_payload(no), max_shares=4,
    )
    assert not result.executable
    assert result.reason


@pytest.mark.parametrize("cap", [0, -1])
def test_nonpositive_cap_has_no_depth(cap):
    result = within_venue_arbitrage(offers((0.4, 10)), offers((0.5, 10)), max_shares=cap)
    assert not result.executable
    assert result.reason == "no depth"
    assert result.shares == result.cost == result.payout == 0
    assert math.isnan(result.net_edge)


def test_fee_rate_can_turn_a_valid_pair_into_a_loss():
    yes, no = offers((0.49, 10)), offers((0.49, 10))
    assert within_venue_arbitrage(yes, no).executable
    result = within_venue_arbitrage(yes, no, fee_rate=0.03)
    assert result.fees == pytest.approx(0.294)
    assert result.profit == pytest.approx(-0.094)
    assert not result.executable
    assert result.reason == "costs exceed the edge"


def test_no_leg_depth_also_limits_both_costs():
    result = within_venue_arbitrage(offers((0.4, 100)), offers((0.5, 2)))
    assert result.shares == result.payout == 2
    assert result.cost == pytest.approx(1.8)
    assert result.profit == pytest.approx(0.2)


def test_slippage_adds_the_cost_of_walking_both_legs():
    result = within_venue_arbitrage(
        offers((0.4, 2), (0.45, 2)), offers((0.5, 1), (0.55, 3)), max_shares=4,
    )
    # YES slips by 2 * 0.05, NO by 3 * 0.05; both are costs.
    assert result.slippage_cost == pytest.approx(0.25)
    assert result.profit == pytest.approx(0.15)
    assert result.executable


@pytest.mark.parametrize("odds", [0, -2])
def test_nonpositive_kelly_odds_have_no_stake(odds):
    assert kelly_fraction(0.6, odds) == 0


def test_binary_kelly_uses_return_per_dollar_staked():
    # At 25 cents a win earns 3 dollars per dollar staked; p=q=1/2.
    assert kelly_for_binary_contract(0.25, 0.5) == pytest.approx(1 / 3)


def test_negative_contract_count_has_no_fee():
    assert kalshi_fee(0.5, -100) == 0
