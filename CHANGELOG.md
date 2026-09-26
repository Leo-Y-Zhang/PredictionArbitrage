# Changelog

Notable changes to this project, in the format of
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

The project has never been tagged for release, so there are no version headings
yet, only *Unreleased*. Back-filling release notes for work that shipped without
them would be writing history after the fact, which is the thing this
repository's documents are meant not to do.

## [Unreleased]

### Added

- **CLI** (`predarb scan|book|price|verify`), including an offline `price`
  command that costs a hypothetical pair with no network access.
- **Pair-sum distribution** recorded alongside the arbitrage count, so a result
  of zero can be told apart from a broken scanner.

### Fixed

- **Floating-point comparisons at the boundaries.** `1.01 - 1.0` evaluates to
  0.010000000000000009, so every pair exactly one cent from 1 fell outside the
  "within one cent" bucket (and two cents out, the two-cent bucket). The same
  problem rejected trades whose profit was exactly `min_profit`. Both
  comparisons now round to well below a tick first. The published scan, whose
  pair sums are 1.001-1.002, is unaffected.
- **Kalshi fee rounding.** `0.07 * 100 * 0.5 * 0.5` evaluates to
  1.7500000000000002 in binary floating point, so taking the ceiling without
  rounding first billed 1.76 for a fee that is exactly 1.75. The error was
  always upward, so it silently overstated costs on every round number.

