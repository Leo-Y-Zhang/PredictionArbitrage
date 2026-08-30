# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""Costed arbitrage detection for prediction markets."""
from .arb import cross_venue_edge, kelly_fraction, within_venue_arbitrage
from .book import Level, OrderBook

__all__ = ["OrderBook", "Level", "within_venue_arbitrage",
           "cross_venue_edge", "kelly_fraction"]
__version__ = "0.1.0"
