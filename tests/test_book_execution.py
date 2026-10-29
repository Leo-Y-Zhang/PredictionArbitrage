# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""Exact small-book arithmetic, including the previously untested sell side."""
import math

import pytest

from predarb.book import Level, OrderBook


@pytest.fixture
def book():
    return OrderBook(
        bids=[Level(0.3, 5), Level(0.4, 2)],
        asks=[Level(0.7, 11), Level(0.5, 3)],
    )


def test_quotes_depth_and_weighted_mid_obey_the_selected_depth(book):
    assert book.spread == pytest.approx(0.1)
    assert book.mid == pytest.approx(0.45)
    assert book.bid_depth() == 7
    assert book.ask_depth() == 14
    assert book.liquidity_weighted_mid(depth=1) == pytest.approx(0.46)
    assert book.liquidity_weighted_mid(depth=2) == pytest.approx(11.5 / 21)
    assert book.liquidity_weighted_mid(depth=0) is None
    assert OrderBook().liquidity_weighted_mid() is None


@pytest.mark.parametrize("side", ["bids", "asks"])
def test_one_sided_book_has_no_mid_or_spread(side):
    book = OrderBook(**{side: [Level(0.4, 3)]})
    assert book.mid is None
    assert book.spread is None


@pytest.mark.parametrize("shares,filled,proceeds", [(1, 1, 0.4), (2, 2, 0.8), (4, 4, 1.4), (20, 7, 2.3)])
def test_sell_walks_highest_bids_and_never_overfills(book, shares, filled, proceeds):
    assert book.walk_bids(shares) == pytest.approx((filled, proceeds, proceeds / filled))
    # Quotes describe resting liquidity; walking them must not consume the fixture.
    assert book.bid_depth() == 7


@pytest.mark.parametrize("method", ["walk_bids", "walk_asks"])
@pytest.mark.parametrize("shares", [0, -2])
def test_nonpositive_order_has_no_fill(book, method, shares):
    filled, value, avg = getattr(book, method)(shares)
    assert filled == value == 0
    assert math.isnan(avg)


def test_empty_books_have_no_fill_or_slippage():
    book = OrderBook()
    for walk in (book.walk_bids, book.walk_asks):
        filled, value, avg = walk(2)
        assert filled == value == 0
        assert math.isnan(avg)
    assert math.isnan(book.slippage(2))


def test_parser_discards_negative_and_zero_sizes_on_both_sides():
    rows = [{"price": "0.01", "size": "-2"},
            {"price": "0.02", "size": "0"},
            {"price": "0.4", "size": "3"}]
    book = OrderBook.from_payload({"bids": rows, "asks": rows})
    assert book.bids == book.asks == [Level(0.4, 3)]


@pytest.mark.parametrize("row,error", [
    ({"price": "0.4"}, KeyError),
    ({"size": "3"}, KeyError),
    ({"price": "bad", "size": "3"}, ValueError),
    ({"price": "0.4", "size": "bad"}, ValueError),
])
def test_incomplete_or_nonnumeric_level_is_rejected(row, error):
    assert OrderBook.from_payload({"asks": [{"price": "0.4", "size": "3"}]}).best_ask == 0.4
    with pytest.raises(error):
        OrderBook.from_payload({"asks": [row]})
