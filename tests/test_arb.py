# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""Tests built on hand-computable order books.

Every fixture here has an answer that can be worked out on paper, so a failure
points at the code rather than at a disagreement about what the right answer is.
"""
from __future__ import annotations

import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from predarb.arb import (  # noqa: E402
    cross_venue_edge,
    kalshi_fee,
    kelly_for_binary_contract,
    kelly_fraction,
    polymarket_fee,
    within_venue_arbitrage,
)
from predarb.book import Level, OrderBook  # noqa: E402


def book(bids, asks):
    return OrderBook(bids=[Level(p, s) for p, s in bids],
                     asks=[Level(p, s) for p, s in asks])


class TestOrderBookOrdering(unittest.TestCase):
    def test_asks_are_sorted_best_first_whatever_the_input_order(self):
        """Polymarket returns asks descending; quoting the raw first element
        would report the worst price in the book as the best."""
        b = OrderBook.from_payload({
            "bids": [{"price": "0.001", "size": "40"}],
            "asks": [{"price": "0.999", "size": "259"},
                     {"price": "0.998", "size": "97"},
                     {"price": "0.95", "size": "34000"}],
        })
        self.assertAlmostEqual(b.best_ask, 0.95)

    def test_bids_are_sorted_highest_first(self):
        b = book([(0.30, 10), (0.45, 5), (0.40, 7)], [(0.60, 10)])
        self.assertAlmostEqual(b.best_bid, 0.45)

    def test_zero_size_levels_are_dropped(self):
        b = OrderBook.from_payload({"bids": [], "asks": [
            {"price": "0.10", "size": "0"}, {"price": "0.20", "size": "5"}]})
        self.assertAlmostEqual(b.best_ask, 0.20)

    def test_empty_book_reports_none(self):
        b = book([], [])
        self.assertIsNone(b.best_bid)
        self.assertIsNone(b.best_ask)
        self.assertIsNone(b.spread)
        self.assertIsNone(b.mid)


class TestWalkingTheBook(unittest.TestCase):
    def setUp(self):
        self.b = book([(0.40, 100)], [(0.50, 10), (0.55, 20), (0.70, 100)])

    def test_fill_inside_the_top_level_pays_the_top_price(self):
        filled, cost, avg = self.b.walk_asks(5)
        self.assertAlmostEqual(filled, 5)
        self.assertAlmostEqual(cost, 2.5)
        self.assertAlmostEqual(avg, 0.50)

    def test_fill_across_levels_is_a_weighted_average(self):
        # 10 @ 0.50 + 20 @ 0.55 = 5.0 + 11.0 = 16.0 for 30 shares
        filled, cost, avg = self.b.walk_asks(30)
        self.assertAlmostEqual(filled, 30)
        self.assertAlmostEqual(cost, 16.0)
        self.assertAlmostEqual(avg, 16.0 / 30.0)

    def test_slippage_is_average_minus_best(self):
        self.assertAlmostEqual(self.b.slippage(30), 16.0 / 30.0 - 0.50)

    def test_slippage_is_zero_inside_the_top_level(self):
        self.assertAlmostEqual(self.b.slippage(5), 0.0)

    def test_oversized_order_fills_only_what_exists(self):
        filled, cost, avg = self.b.walk_asks(1000)
        self.assertAlmostEqual(filled, 130)
        self.assertAlmostEqual(cost, 10 * 0.50 + 20 * 0.55 + 100 * 0.70)

    def test_max_size_within_a_limit(self):
        self.assertAlmostEqual(self.b.max_size_within(0.55), 30)
        self.assertAlmostEqual(self.b.max_size_within(0.49), 0)

    def test_liquidity_weighted_mid_leans_to_the_deep_side(self):
        thin_ask = book([(0.40, 1000)], [(0.60, 1)])
        self.assertLess(thin_ask.liquidity_weighted_mid(), thin_ask.mid)


class TestFees(unittest.TestCase):
    def test_kalshi_fee_peaks_at_a_half(self):
        mid = kalshi_fee(0.50, 1000)
        for p in (0.1, 0.25, 0.75, 0.9):
            self.assertLess(kalshi_fee(p, 1000), mid)

    def test_kalshi_fee_matches_the_published_formula(self):
        # 0.07 * 100 * 0.5 * 0.5 = 1.75 exactly, no rounding up needed
        self.assertAlmostEqual(kalshi_fee(0.50, 100), 1.75)

    def test_kalshi_fee_rounds_up_to_the_cent(self):
        raw = 0.07 * 3 * 0.37 * 0.63
        self.assertAlmostEqual(kalshi_fee(0.37, 3), math.ceil(raw * 100) / 100)
        self.assertGreaterEqual(kalshi_fee(0.37, 3), raw)

    def test_kalshi_fee_vanishes_at_the_extremes(self):
        self.assertAlmostEqual(kalshi_fee(0.0, 1000), 0.0)
        self.assertAlmostEqual(kalshi_fee(1.0, 1000), 0.0)

    def test_no_contracts_no_fee(self):
        self.assertEqual(kalshi_fee(0.5, 0), 0.0)

    def test_polymarket_fee_is_zero_by_default(self):
        self.assertEqual(polymarket_fee(0.5, 1000), 0.0)

    def test_polymarket_fee_scales_when_a_rate_is_supplied(self):
        self.assertAlmostEqual(polymarket_fee(0.5, 100, fee_rate=0.02), 1.0)


class TestKelly(unittest.TestCase):
    def test_even_money_coin_with_an_edge(self):
        # b=1, p=0.6 -> f* = (1*0.6 - 0.4)/1 = 0.2
        self.assertAlmostEqual(kelly_fraction(0.6, 1.0), 0.2)

    def test_no_edge_means_no_stake(self):
        self.assertAlmostEqual(kelly_fraction(0.5, 1.0), 0.0)

    def test_negative_edge_is_clipped_to_zero(self):
        self.assertEqual(kelly_fraction(0.4, 1.0), 0.0)

    def test_contract_priced_at_fair_value_gets_no_stake(self):
        self.assertAlmostEqual(kelly_for_binary_contract(0.40, 0.40), 0.0,
                               places=12)

    def test_underpriced_contract_gets_a_positive_stake(self):
        self.assertGreater(kelly_for_binary_contract(0.40, 0.55), 0.0)

    def test_degenerate_prices_are_refused(self):
        self.assertEqual(kelly_for_binary_contract(0.0, 0.5), 0.0)
        self.assertEqual(kelly_for_binary_contract(1.0, 0.5), 0.0)


class TestWithinVenueArbitrage(unittest.TestCase):
    def test_clear_arbitrage_is_found_and_costed(self):
        """YES at 0.45 and NO at 0.50 cost 0.95 for a pair worth 1.00."""
        yes = book([], [(0.45, 100)])
        no = book([], [(0.50, 100)])
        r = within_venue_arbitrage(yes, no, venue="polymarket", max_shares=100)
        self.assertAlmostEqual(r.gross_edge, 0.05)
        self.assertAlmostEqual(r.shares, 100)
        self.assertAlmostEqual(r.cost, 95.0)
        self.assertAlmostEqual(r.payout, 100.0)
        self.assertAlmostEqual(r.profit, 5.0)
        self.assertTrue(r.executable)

    def test_no_arbitrage_when_the_pair_costs_more_than_one(self):
        yes = book([], [(0.55, 100)])
        no = book([], [(0.50, 100)])
        r = within_venue_arbitrage(yes, no, max_shares=100)
        self.assertLess(r.gross_edge, 0)
        self.assertFalse(r.executable)

    def test_gas_can_eat_the_whole_edge(self):
        """A 0.5 cent per pair edge on 100 shares is 50 cents; $5 of gas kills it."""
        yes = book([], [(0.4975, 100)])
        no = book([], [(0.4975, 100)])
        cheap = within_venue_arbitrage(yes, no, max_shares=100, gas=0.0)
        pricey = within_venue_arbitrage(yes, no, max_shares=100, gas=5.0)
        self.assertTrue(cheap.executable)
        self.assertFalse(pricey.executable)
        self.assertAlmostEqual(pricey.profit, cheap.profit - 5.0)

    def test_slippage_can_eat_the_edge(self):
        """Top of book shows a 4 cent edge, but only 1 share deep."""
        yes = book([], [(0.46, 1), (0.60, 500)])
        no = book([], [(0.50, 1), (0.60, 500)])
        top_only = within_venue_arbitrage(yes, no, max_shares=1)
        for_size = within_venue_arbitrage(yes, no, max_shares=200)
        self.assertTrue(top_only.executable)
        self.assertGreater(for_size.slippage_cost, 0)
        self.assertFalse(for_size.executable,
                         "walking into 0.60 asks must destroy the edge")

    def test_kalshi_fees_are_applied(self):
        yes = book([], [(0.48, 1000)])
        no = book([], [(0.48, 1000)])
        poly = within_venue_arbitrage(yes, no, venue="polymarket", max_shares=1000)
        kal = within_venue_arbitrage(yes, no, venue="kalshi", max_shares=1000)
        self.assertGreater(poly.profit, kal.profit)
        self.assertAlmostEqual(kal.fees, 2 * kalshi_fee(0.48, 1000))

    def test_size_is_capped_by_the_thinner_side(self):
        yes = book([], [(0.45, 10)])
        no = book([], [(0.50, 1000)])
        r = within_venue_arbitrage(yes, no, max_shares=1000)
        self.assertAlmostEqual(r.shares, 10)

    def test_missing_side_is_reported_not_crashed(self):
        r = within_venue_arbitrage(book([], []), book([], [(0.5, 10)]))
        self.assertFalse(r.executable)
        self.assertIn("no offers", r.reason)


class TestCrossVenue(unittest.TestCase):
    def test_edge_is_one_minus_the_pair(self):
        self.assertAlmostEqual(cross_venue_edge(0.45, 0.50), 0.05)

    def test_no_edge_when_consistent(self):
        self.assertAlmostEqual(cross_venue_edge(0.60, 0.40), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestEndToEndFromVenuePayload(unittest.TestCase):
    """A null result is only worth reading if the pipeline can find a positive.

    These drive raw venue-shaped payloads through the same path the live
    scanner uses, including Polymarket's descending ask ordering.
    """

    def test_detects_an_arbitrage_injected_as_a_raw_payload(self):
        yes = OrderBook.from_payload({
            "bids": [{"price": "0.40", "size": "100"}],
            # descending, as Polymarket returns them
            "asks": [{"price": "0.80", "size": "500"},
                     {"price": "0.44", "size": "200"}],
        })
        no = OrderBook.from_payload({
            "bids": [{"price": "0.48", "size": "100"}],
            "asks": [{"price": "0.90", "size": "500"},
                     {"price": "0.50", "size": "200"}],
        })
        r = within_venue_arbitrage(yes, no, venue="polymarket",
                                   max_shares=200, gas=0.02)
        self.assertAlmostEqual(r.gross_edge, 0.06, places=9)
        self.assertTrue(r.executable)
        self.assertAlmostEqual(r.profit, 200 * 0.06 - 0.02, places=6)

    def test_a_market_priced_one_tick_wide_is_not_an_arbitrage(self):
        """What the live scan actually observes: pairs summing to 1.001."""
        yes = OrderBook.from_payload({"bids": [], "asks": [{"price": "0.5005",
                                                           "size": "1000"}]})
        no = OrderBook.from_payload({"bids": [], "asks": [{"price": "0.5005",
                                                          "size": "1000"}]})
        r = within_venue_arbitrage(yes, no, max_shares=1000, gas=0.02)
        self.assertAlmostEqual(r.gross_edge, -0.001, places=9)
        self.assertFalse(r.executable)
