"""Costed arbitrage detection for prediction markets."""
from .book import OrderBook, Level
from .arb import within_venue_arbitrage, cross_venue_edge, kelly_fraction

__all__ = ["OrderBook", "Level", "within_venue_arbitrage",
           "cross_venue_edge", "kelly_fraction"]
__version__ = "0.1.0"
