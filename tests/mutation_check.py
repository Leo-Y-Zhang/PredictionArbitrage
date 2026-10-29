# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""Selected, reproducible first-order mutations, each run in an isolated copy.

Run with the same Python environment used for CI (including pytest and ruff):
    python tests/mutation_check.py before
    python tests/mutation_check.py after

The original sources are never edited. Results include the first rejecting
gate command; a timeout is reported separately and never counted as a kill.
This is a targeted experiment, not an exhaustive mutation score.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# (module, identifier, original, replacement). Each original must occur once.
MUTANTS = [
    ("src/predarb/arb.py", "negative-contract-fee", "if contracts <= 0:", "if contracts == 0:"),
    ("src/predarb/arb.py", "zero-contract-boundary", "if contracts <= 0:", "if contracts < 0:"),
    ("src/predarb/arb.py", "fee-round-down", "math.ceil(round(raw_cents, 9))", "math.floor(round(raw_cents, 9))"),
    ("src/predarb/arb.py", "fee-no-decimal-rounding", "math.ceil(round(raw_cents, 9))", "math.ceil(raw_cents)"),
    ("src/predarb/arb.py", "kelly-zero-odds", "if b <= 0:", "if b < 0:"),
    ("src/predarb/arb.py", "kelly-negative-odds", "if b <= 0:", "if b == 0:"),
    ("src/predarb/arb.py", "kelly-wrong-odds", "(1.0 - price) / price)", "(1.0 - price))"),
    ("src/predarb/arb.py", "missing-leg-and", "if ya is None or na is None:", "if ya is None and na is None:"),
    ("src/predarb/arb.py", "ignore-size-cap", "no_book.ask_depth(), max_shares)", "no_book.ask_depth())"),
    ("src/predarb/arb.py", "max-depth", "depth = min(", "depth = max("),
    ("src/predarb/arb.py", "zero-depth-boundary", "if depth <= 0:", "if depth < 0:"),
    ("src/predarb/arb.py", "ignore-fee-rate", "fee_fn(y_avg, shares, fee_rate) + fee_fn(n_avg, shares, fee_rate)", "fee_fn(y_avg, shares, 0) + fee_fn(n_avg, shares, 0)"),
    ("src/predarb/arb.py", "omit-no-leg-fee", "fee_fn(y_avg, shares) + fee_fn(n_avg, shares)", "fee_fn(y_avg, shares)"),
    ("src/predarb/arb.py", "add-fees-to-profit", "profit = payout - cost - fees - gas", "profit = payout - cost + fees - gas"),
    ("src/predarb/arb.py", "omit-gas", "profit = payout - cost - fees - gas", "profit = payout - cost - fees"),
    ("src/predarb/arb.py", "profit-strict-boundary", "round(profit, 9) >= min_profit", "round(profit, 9) > min_profit"),
    ("src/predarb/arb.py", "accept-all-results", "round(profit, 9) >= min_profit", "True"),
    ("src/predarb/arb.py", "net-edge-multiplied", "net_edge = profit / shares", "net_edge = profit * shares"),
    ("src/predarb/arb.py", "slippage-no-leg-subtracted", "slip = (y_avg - ya) * shares + (n_avg - na) * shares", "slip = (y_avg - ya) * shares - (n_avg - na) * shares"),
    ("src/predarb/book.py", "reverse-asks", "self.asks, key=lambda lv: lv.price", "self.asks, key=lambda lv: -lv.price"),
    ("src/predarb/book.py", "accept-negative-size", "if size > 0:", "if size != 0:"),
    ("src/predarb/book.py", "accept-zero-size", "if size > 0:", "if size >= 0:"),
    ("src/predarb/book.py", "price-used-as-size", 'size = float(r["size"])', 'size = float(r["price"])'),
    ("src/predarb/book.py", "missing-size-default", 'size = float(r["size"])', 'size = float(r.get("size", 1))'),
    ("src/predarb/book.py", "spread-added", "return self.best_ask - self.best_bid", "return self.best_ask + self.best_bid"),
    ("src/predarb/book.py", "mid-subtracted", "0.5 * (self.best_bid + self.best_ask)", "0.5 * (self.best_bid - self.best_ask)"),
    ("src/predarb/book.py", "one-sided-spread", "def spread(self):\n        if self.best_bid is None or self.best_ask is None:", "def spread(self):\n        if self.best_bid is None and self.best_ask is None:"),
    ("src/predarb/book.py", "weighted-depth-off-by-one", "self.bids[:depth] + self.asks[:depth]", "self.bids[:depth + 1] + self.asks[:depth + 1]"),
    ("src/predarb/book.py", "empty-weighted-mid", "if total <= 0:", "if total < 0:"),
    ("src/predarb/book.py", "bid-depth-from-asks", "def bid_depth(self):\n        return sum(lv.size for lv in self.bids)", "def bid_depth(self):\n        return sum(lv.size for lv in self.asks)"),
    ("src/predarb/book.py", "sell-into-asks", "for level in self.bids:", "for level in self.asks:"),
    ("src/predarb/book.py", "sell-proceeds-subtracted", "proceeds += take * level.price", "proceeds -= take * level.price"),
    ("src/predarb/book.py", "sell-overfills", "remaining, proceeds = float(shares), 0.0\n        for level in self.bids:\n            if remaining <= 0:\n                break\n            take = min(remaining, level.size)", "remaining, proceeds = float(shares), 0.0\n        for level in self.bids:\n            if remaining <= 0:\n                break\n            take = max(remaining, level.size)"),
    ("src/predarb/book.py", "buy-stop-at-zero", "remaining, cost = float(shares), 0.0\n        for level in self.asks:\n            if remaining <= 0:", "remaining, cost = float(shares), 0.0\n        for level in self.asks:\n            if remaining < 0:"),
    ("src/predarb/scanner.py", "below-includes-boundary", "if g < 0)", "if g <= 0)"),
    ("src/predarb/scanner.py", "one-cent-strict", "abs(g) <= 0.01", "abs(g) < 0.01"),
    ("src/predarb/scanner.py", "percentile-off-by-one", "int(0.05 * len(s)) - 1", "int(0.05 * len(s))"),
    ("src/predarb/scanner.py", "maximum-is-minimum", '"max": s[-1]', '"max": s[0]'),
    ("src/predarb/scanner.py", "skip-empty-stats-check", "if not sums:", "if sums:"),
    ("src/predarb/scanner.py", "ignore-book-failure", "failed += 1", "failed += 0"),
    ("src/predarb/scanner.py", "wrong-scanned-count", "scanned += 1", "scanned += 0"),
    ("src/predarb/scanner.py", "one-sided-pair-sum", "yb.best_ask is not None and nb.best_ask is not None", "yb.best_ask is not None or nb.best_ask is not None"),
    ("src/predarb/scanner.py", "gross-includes-zero", "r.gross_edge > 0:", "r.gross_edge >= 0:"),
    ("src/predarb/scanner.py", "count-nonexecutable", "if r.executable:", "if not r.executable:"),
    ("src/predarb/scanner.py", "reverse-profit-ranking", 'key=lambda r: -r["profit"]', 'key=lambda r: r["profit"]'),
    ("src/predarb/scanner.py", "wrong-survival-denominator", "(net_hits / gross_hits) if gross_hits else None", "(net_hits / scanned) if gross_hits else None"),
    ("src/predarb/polymarket.py", "binary-filter-and", "len(tokens) != 2 or len(outcomes) != 2", "len(tokens) != 2 and len(outcomes) != 2"),
    ("src/predarb/polymarket.py", "token-count-inverted", "len(tokens) != 2 or len(outcomes) != 2", "len(tokens) == 2 or len(outcomes) != 2"),
    ("src/predarb/polymarket.py", "outcome-count-inverted", "len(tokens) != 2 or len(outcomes) != 2", "len(tokens) != 2 or len(outcomes) == 2"),
    ("src/predarb/polymarket.py", "liquidity-strict-boundary", 'float(m.get("liquidityNum") or 0) < min_liquidity:', 'float(m.get("liquidityNum") or 0) <= min_liquidity:'),
    ("src/predarb/polymarket.py", "liquidity-inverted", 'float(m.get("liquidityNum") or 0) < min_liquidity:', 'float(m.get("liquidityNum") or 0) > min_liquidity:'),
    ("src/predarb/polymarket.py", "cache-use-or", 'f"markets_{limit}_{int(min_liquidity)}.json")\n    if use_cache and os.path.exists(path):', 'f"markets_{limit}_{int(min_liquidity)}.json")\n    if use_cache or os.path.exists(path):' ),
    ("src/predarb/polymarket.py", "ignore-book-refresh", "def order_book(token_id, use_cache=True):\n    os.makedirs(CACHE_DIR, exist_ok=True)\n    path = os.path.join(CACHE_DIR, f\"book_{token_id[:24]}.json\")\n    if use_cache and os.path.exists(path):", "def order_book(token_id, use_cache=True):\n    os.makedirs(CACHE_DIR, exist_ok=True)\n    path = os.path.join(CACHE_DIR, f\"book_{token_id[:24]}.json\")\n    if os.path.exists(path):"),
    ("src/predarb/polymarket.py", "book-cache-off-by-one", "token_id[:24]", "token_id[:23]"),
    ("scripts/check_spdx.py", "header-window-too-short", "range(5)", "range(4)"),
    ("scripts/check_spdx.py", "header-window-too-long", "range(5)", "range(6)"),
    ("scripts/check_spdx.py", "accept-missing-header", "    return False\n", "    return True\n"),
    ("scripts/check_spdx.py", "reject-valid-header", "if IDENTIFIER in line:", "if IDENTIFIER not in line:"),
    ("scripts/check_spdx.py", "skip-tests", '"src/**/*.py", "tests/**/*.py", "scripts/**/*.py"', '"src/**/*.py", "src/**/*.py", "scripts/**/*.py"'),
    ("scripts/check_spdx.py", "missing-header-success", "    return 1\n", "    return 0\n"),
    ("src/predarb/__main__.py", "verify-always-succeeds", "return 0 if ok.wasSuccessful() else 1", "return 0 if ok.wasSuccessful() else 0"),
    ("src/predarb/__main__.py", "verify-always-fails", "return 0 if ok.wasSuccessful() else 1", "return 1 if ok.wasSuccessful() else 1"),
]


def gate_commands(phase):
    python = sys.executable
    commands = [
        [python, "scripts/check_spdx.py"],
        [python, "-m", "ruff", "check", "."],
        [python, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [python, "-m", "predarb", "--help"],
        [python, "-m", "predarb", "price", "0.45", "0.50", "--shares", "100"],
        [python, "-m", "predarb", "verify"],
    ]
    if phase == "after":
        commands.append([python, "-m", "pytest", "-q"])
    return commands


def run_gate(workspace, phase):
    env = {**os.environ, "PYTHONPATH": str(workspace / "src"),
           "PYTHONDONTWRITEBYTECODE": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    for command in gate_commands(phase):
        label = "python " + " ".join(command[1:])
        try:
            result = subprocess.run(command, cwd=workspace, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    timeout=60)
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "command": label}
        if result.returncode:
            # Only relative paths and a concise failure summary go into the report.
            failures = [line for line in result.stdout.splitlines()
                        if line.startswith(("FAILED ", "FAIL:", "ERROR:"))]
            return {"status": "killed", "command": label, "failures": failures}
    return {"status": "survived"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("before", "after"))
    parser.add_argument("--only", nargs="+", help="rerun named mutants and merge their results")
    args = parser.parse_args()
    if args.only and set(args.only) - {m[1] for m in MUTANTS}:
        parser.error("unknown mutant identifier")
    report_path = ROOT / "tests" / "mutation_results.json"
    report = json.loads(report_path.read_text()) if report_path.exists() else {}
    with tempfile.TemporaryDirectory(prefix=".mutation-", dir=ROOT) as temp:
        workspace = Path(temp)
        for directory in ("src", "tests", "scripts"):
            shutil.copytree(ROOT / directory, workspace / directory,
                            ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
        if args.phase == "before":
            # Recreate the original suite even when rerunning this experiment
            # after the additional tests have been checked out.
            for path in (workspace / "tests").glob("test_*.py"):
                if path.name != "test_arb.py":
                    path.unlink()
            (workspace / "tests" / "conftest.py").unlink(missing_ok=True)
        shutil.copy2(ROOT / "pyproject.toml", workspace)
        baseline = run_gate(workspace, args.phase)
        if baseline["status"] != "survived":
            raise SystemExit(f"Unmutated gate failed: {baseline}")
        results = []
        for module, identifier, original, replacement in MUTANTS:
            if args.only and identifier not in args.only:
                continue
            path = workspace / module
            source = path.read_text()
            if source.count(original) != 1:
                raise SystemExit(f"{identifier}: expected exactly one mutation site")
            line = source[:source.index(original)].count("\n") + 1
            try:
                mutated = source.replace(original, replacement, 1)
                compile(mutated, module, "exec")
                path.write_text(mutated)
                result = run_gate(workspace, args.phase)
            finally:
                path.write_text(source)
            results.append({"module": module, "id": identifier, "line": line, **result})
            print(f"{args.phase}: {module}:{line} {identifier}: {result['status']}", flush=True)
    merged = {r["id"]: r for r in report.get(args.phase, [])} if args.only else {}
    merged.update({r["id"]: r for r in results})
    report[args.phase] = [merged[m[1]] for m in MUTANTS if m[1] in merged]
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    for module in dict.fromkeys(m[0] for m in MUTANTS):
        rows = [r for r in report[args.phase] if r["module"] == module]
        killed = sum(r["status"] == "killed" for r in rows)
        print(f"{module}: {killed}/{len(rows)} killed")


if __name__ == "__main__":
    main()
