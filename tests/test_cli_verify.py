# SPDX-License-Identifier: LicenseRef-Leo-Y-Zhang-Proprietary
"""A failing offline suite must propagate failure through the verify command."""
import unittest

import pytest

from predarb.__main__ import main


@pytest.mark.parametrize("fails", [False, True])
def test_verify_exit_status_matches_the_test_result(monkeypatch, capsys, fails):
    class Probe(unittest.TestCase):
        def runTest(self):
            if fails:
                self.fail("injected failing check")

    def discover(loader, start_dir):
        assert start_dir == "tests"
        return unittest.TestSuite([Probe()])

    monkeypatch.setattr(unittest.TestLoader, "discover", discover)
    assert main(["verify"]) == (1 if fails else 0)
    stderr = capsys.readouterr().err
    assert "Ran 1 test" in stderr
    assert ("FAILED (failures=1)" if fails else "OK") in stderr
