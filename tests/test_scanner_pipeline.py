# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""Exercise scan decisions and persisted counts with tiny, injected venue data."""
import json

import pytest

from predarb import scanner


def test_distribution_values_and_percentile_rank():
    sums = [i / 100 for i in reversed(range(80, 120))]
    original = sums.copy()
    assert scanner.pair_sum_stats(sums) == pytest.approx({
        "n": 40, "min": 0.8, "max": 1.19, "p05": 0.81,
        "median": 0.995, "mean": 0.995, "n_below_1": 20,
        "n_within_1c_of_1": 3, "n_within_2c_of_1": 5,
    })
    assert sums == original
    assert scanner.pair_sum_stats([]) is None
    assert scanner.pair_sum_stats([1])["p05"] == 1


@pytest.mark.parametrize("refresh", [False, True])
@pytest.mark.parametrize("fee_rate,min_profit,net_hits", [(0, 0.01, 2), (0.02, 1, 1)])
def test_scan_counts_only_costed_opportunities_and_records_failures(
    tmp_path, monkeypatch, capsys, refresh, fee_rate, min_profit, net_hits,
):
    names = ["low", "high", "thin", "fair", "empty", "broken"]
    markets = [{"question": name, "condition_id": name, "liquidity": 500,
                "token_ids": [f"{name}-yes", f"{name}-no"]} for name in names]
    metadata_calls, book_calls = [], []

    def active_markets(limit, min_liquidity, use_cache):
        metadata_calls.append((limit, min_liquidity, use_cache))
        return markets

    def order_book(token, use_cache):
        book_calls.append((token, use_cache))
        name, side = token.split("-")
        if name == "broken":
            return {"asks": [{"price": "bad", "size": "10"}]}
        if name == "empty" and side == "no":
            return {"asks": []}
        price = {"low": "0.4", "high": "0.3", "thin": "0.499"}.get(name, "0.5")
        return {"asks": [{"price": price if side == "yes" else "0.5", "size": "10"}]}

    monkeypatch.setattr(scanner.polymarket, "active_markets", active_markets)
    monkeypatch.setattr(scanner.polymarket, "order_book", order_book)
    out_path = tmp_path / "result.json"
    result = scanner.run(
        limit=6, min_liquidity=500, max_shares=10, gas=0.1,
        fee_rate=fee_rate, min_profit=min_profit, refresh=refresh,
        quiet=True, out_path=out_path,
    )
    assert metadata_calls == [(6, 500, not refresh)]
    assert len(book_calls) == 11
    assert all(use_cache == (not refresh) for _, use_cache in book_calls)
    assert result["n_markets"] == 6
    assert result["n_scanned"] == 5
    assert result["n_book_failures"] == 1
    assert result["n_gross_edges"] == 3
    assert result["n_executable"] == net_hits
    assert result["survival_rate"] == pytest.approx(net_hits / 3)
    assert result["pair_sum_distribution"]["n"] == 4
    assert result["pair_sum_distribution"]["n_below_1"] == 3
    assert result["params"] == {
        "limit": 6, "min_liquidity": 500, "max_shares": 10, "gas": 0.1,
        "fee_rate": fee_rate, "min_profit": min_profit,
    }
    rows = result["opportunities"]
    assert [row["question"] for row in rows] == ["high", "low", "thin"]
    assert [row["executable"] for row in rows] == [True, net_hits == 2, False]
    assert rows[0]["profit"] == pytest.approx(1.9 - 8 * fee_rate)
    assert rows[-1]["profit"] < 0
    assert json.loads(out_path.read_text()) == result
    assert capsys.readouterr().out == ""


def test_empty_scan_has_no_survival_rate_or_distribution(tmp_path, monkeypatch):
    monkeypatch.setattr(scanner.polymarket, "active_markets", lambda *a, **kw: [])
    result = scanner.run(quiet=True, out_path=tmp_path / "empty.json")
    assert result["n_markets"] == result["n_scanned"] == result["n_book_failures"] == 0
    assert result["n_gross_edges"] == result["n_executable"] == 0
    assert result["survival_rate"] is None
    assert result["pair_sum_distribution"] is None
    assert result["opportunities"] == []
