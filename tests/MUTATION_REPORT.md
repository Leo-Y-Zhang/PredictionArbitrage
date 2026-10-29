# Mutation-guided unit tests

Six pytest files (plus a `conftest.py`), a reproducible mutation runner
(`tests/mutation_check.py`) and its per-mutant results
(`tests/mutation_results.json`). Production code is unchanged. CI now installs
pytest 8.4.2 and runs `pytest -q` beside the existing unittest step.

## Measurement

`python tests/mutation_check.py before` runs the original CI gate against each
mutant: the SPDX check, ruff, unittest, and the CLI checks (`--help`, `price`,
`verify`). `after` adds `pytest -q`, which is what runs the new pytest-style
tests. Each
mutant is applied alone in a temporary copy; the original sources are never
edited, and a timeout is never counted as a kill.

| Module | Mutants tried | Killed before | Killed after |
| --- | ---: | ---: | ---: |
| `src/predarb/arb.py` | 19 | 11 | 18 |
| `src/predarb/book.py` | 15 | 4 | 14 |
| `src/predarb/scanner.py` | 12 | 3 | 12 |
| `src/predarb/polymarket.py` | 8 | 0 | 8 |
| `scripts/check_spdx.py` | 6 | 0 | 6 |
| `src/predarb/__main__.py` | 2 | 1 | 2 |
| **Total** | **62** | **19** | **60** |

The two survivors are equivalent mutants and cannot be killed:

- `arb.py:22` `zero-contract-boundary` (`contracts <= 0` to `< 0`): with zero
  contracts the fee formula already evaluates to exactly 0.
- `book.py:91` `buy-stop-at-zero` (`remaining <= 0` to `< 0`): with nothing
  left to buy, each remaining level takes 0 shares, so fill and cost are unchanged.

This is a targeted sample, not an exhaustive mutation score.

## A killed mutant for every new test file

| Test file | Example mutant killed (module:line, id) |
| --- | --- |
| `test_arb_validation.py` | `arb.py:22` `negative-contract-fee`; `arb.py:51` `kelly-zero-odds` |
| `test_book_execution.py` | `book.py:42` `accept-negative-size`; `book.py:59` `spread-added` |
| `test_scanner_pipeline.py` | `arb.py:126` `ignore-fee-rate`; `scanner.py:30` `percentile-off-by-one` |
| `test_market_validation.py` | `polymarket.py:62` `binary-filter-and` |
| `test_spdx_checker.py` | `check_spdx.py:37` `header-window-too-short`; `check_spdx.py:43` `accept-missing-header` |
| `test_cli_verify.py` | `__main__.py:82` `verify-always-succeeds` |

## Commands and results

Measured on a real checkout with Python 3.13, pytest 8.4.2:

| Command | Result |
| --- | --- |
| `python tests/mutation_check.py before` | 19/62 killed |
| `python tests/mutation_check.py after` | 60/62 killed (2 equivalent) |
| `pytest -q` | 107 passed |
| `python -m unittest discover -s tests` | OK |
| `ruff check .` | All checks passed |
| `python scripts/check_spdx.py` | all source files carry the identifier |
| `git diff --check` | Clean |

No test makes a network request: order books are hand-built, and the one fetch
test replaces `urllib.request.urlopen` with a stub.
