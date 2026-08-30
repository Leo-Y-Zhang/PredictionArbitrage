"""Render README.md from README.template.md and results.json."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))


def count_tests():
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                       cwd=HERE, capture_output=True, text=True, timeout=600)
    m = re.search(r"Ran (\d+) tests", r.stderr or r.stdout)
    if not m or r.returncode != 0:
        sys.exit("test suite must pass before the README is regenerated")
    return int(m.group(1))


res = json.load(open(os.path.join(HERE, "results.json"), encoding="utf-8"))
d = res["pair_sum_distribution"]
if not d:
    sys.exit("results.json has no pair-sum distribution; run scan.py first")

V = {
    "asof": res["asof"][:10],
    "n_scanned": res["n_scanned"],
    "min_liq": f"{res['params']['min_liquidity']:,.0f}",
    "n_gross": res["n_gross_edges"],
    "n_exec": res["n_executable"],
    "n_dist": d["n"],
    "min_sum": f"{d['min']:.4f}",
    "median_sum": f"{d['median']:.4f}",
    "max_sum": f"{d['max']:.4f}",
    "n_below": d["n_below_1"],
    "n_1c": d["n_within_1c_of_1"],
    "n_tests": count_tests(),
}

tpl = open(os.path.join(HERE, "README.template.md"), encoding="utf-8").read()


def sub(m):
    k = m.group(1)
    if k not in V:
        raise KeyError(f"template needs '{k}' but it was not computed")
    return str(V[k])


out = re.sub(r"<<(\w+)>>", sub, tpl)
left = re.findall(r"<<[^>]*>>", out)
if left:
    sys.exit(f"unfilled placeholders: {left}")

open(os.path.join(HERE, "README.md"), "w", encoding="utf-8").write(out)
print(f"wrote README.md ({len(V)} values injected, {V['n_tests']} tests passing)")
